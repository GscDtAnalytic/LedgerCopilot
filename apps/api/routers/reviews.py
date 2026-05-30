"""POST /api/v1/cases/{id}/review — human reviewer actions.

Supports three actions:
  - approve → IN_HUMAN_REVIEW → APPROVED → CLOSED       (approver, admin)
  - reject  → IN_HUMAN_REVIEW → REJECTED → CLOSED       (approver, admin)
  - edit    → IN_HUMAN_REVIEW → EDITED → VALIDATED      (analyst, approver, admin)
              edited_fields saved as new ExtractionResult (source=human)
              pipeline re-enqueued from VALIDATED

Auth required: actor_id derived from JWT; org check on every case access.
RBAC enforced per action: approve/reject require approver or admin.
Every action writes HumanReview + AuditEvent in the same DB transaction.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from packages.domain.entities import ExtractionOutput
from packages.domain.enums import ActorType
from packages.domain.state_machine import (
    CaseStatus,
    InvalidTransitionError,
    assert_transition,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user
from apps.api.database import get_session
from apps.api.models import AuditEvent, Case, HumanReview
from apps.api.schemas.cases import ReviewRequest, ReviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["reviews"])

_ACTION_TO_STATUS: dict[str, CaseStatus] = {
    "approve": CaseStatus.APPROVED,
    "reject": CaseStatus.REJECTED,
    "edit": CaseStatus.EDITED,
}

# RBAC: which roles may perform each action.
_ACTION_ROLES: dict[str, tuple[str, ...]] = {
    "approve": ("approver", "admin"),
    "reject": ("approver", "admin"),
    "edit": ("analyst", "approver", "admin"),
}

_TERMINAL_AFTER: dict[CaseStatus, CaseStatus | None] = {
    CaseStatus.APPROVED: CaseStatus.CLOSED,
    CaseStatus.REJECTED: CaseStatus.CLOSED,
    CaseStatus.EDITED: CaseStatus.VALIDATED,  # re-enters pipeline at VALIDATED
}


def _build_edited_extraction(
    existing_fields_json: dict,
    edited_fields: dict,
) -> ExtractionOutput:
    """Merge human-supplied edits over the existing extraction.

    Human-supplied values are treated as fully trusted: confidence=1.0, source=human.
    """
    merged = dict(existing_fields_json)
    for field_name, raw_value in edited_fields.items():
        if raw_value is None:
            merged[field_name] = None
        else:
            value = raw_value.get("value", raw_value) if isinstance(raw_value, dict) else raw_value
            merged[field_name] = {"value": value, "confidence": 1.0, "source": "human"}
    return ExtractionOutput.model_validate(merged)


@router.post("/{case_id}/review", response_model=ReviewResponse)
async def review_case(
    case_id: str,
    body: ReviewRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReviewResponse:
    """Apply a human review action. Atomic: status + HumanReview + AuditEvent."""
    case = await session.get(Case, case_id)
    if case is None or case.organization_id != user.org_id:
        raise HTTPException(status_code=404, detail="Case not found.")

    if body.action not in _ACTION_TO_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"action must be one of: {list(_ACTION_TO_STATUS)}",
        )

    # RBAC check per action.
    allowed_roles = _ACTION_ROLES[body.action]
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{user.role}' cannot perform action '{body.action}'. "
            f"Required: {list(allowed_roles)}.",
        )

    target = _ACTION_TO_STATUS[body.action]

    try:
        assert_transition(CaseStatus(case.status), target)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # --- Atomic write: HumanReview + Case.status + AuditEvent ---
    review = HumanReview(
        case_id=case.id,
        reviewer_id=user.user_id,
        action=body.action,
        note=body.note,
    )
    session.add(review)

    audit = AuditEvent(
        case_id=case.id,
        organization_id=case.organization_id,
        actor_type=ActorType.HUMAN,
        actor_id=user.user_id,
        from_status=case.status,
        to_status=target,
        trace_id=case.trace_id,
        payload={"action": body.action, "note": body.note or ""},
    )
    case.status = target
    session.add(audit)
    await session.flush()

    # Follow-on transition for each action.
    follow_on = _TERMINAL_AFTER.get(target)
    if follow_on is not None:
        follow_payload: dict = {"reason": "auto-closed after human decision"}

        # For edit: save the corrected fields as a new ExtractionResult.
        if target == CaseStatus.EDITED and body.edited_fields:
            from sqlalchemy import select

            from apps.api.models import ExtractionResult

            existing_row = await session.scalar(
                select(ExtractionResult)
                .where(ExtractionResult.case_id == case_id)
                .order_by(ExtractionResult.created_at.desc())
                .limit(1)
            )
            base_json = existing_row.fields_json if existing_row else {}
            new_fields = _build_edited_extraction(base_json, body.edited_fields)
            corrected = ExtractionResult(
                case_id=case.id,
                fields_json=new_fields.model_dump(),
                prompt_version_id="human-edit",
                model_name="human",
                overall_confidence=new_fields.overall_confidence(),
            )
            session.add(corrected)
            follow_payload = {"reason": "human correction applied; re-entering pipeline"}

        follow_audit = AuditEvent(
            case_id=case.id,
            organization_id=case.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id="review_endpoint",
            from_status=target,
            to_status=follow_on,
            trace_id=case.trace_id,
            payload=follow_payload,
        )
        case.status = follow_on
        session.add(follow_audit)
        await session.flush()

    await session.commit()

    # Prometheus: human review action completed.
    try:
        from packages.observability.metrics import human_reviews_completed_total

        human_reviews_completed_total.labels(action=body.action, org_id=case.organization_id).inc()
    except Exception:
        pass

    #: signal the durable Temporal HITL workflow that review was submitted.
    # Done AFTER commit — DB state is source of truth; signal is additive for SLA tracking.
    # Silently ignores errors (Temporal down, workflow already completed, etc.).
    try:
        from apps.api.temporal_client import signal_hitl_workflow

        await signal_hitl_workflow(
            case_id=case_id,
            action=body.action,
            reviewer_id=user.user_id,
        )
    except Exception as exc:
        logger.debug("review.hitl_signal_skipped case_id=%s reason=%s", case_id, exc)

    # Re-enqueue pipeline when an edit sets case back to VALIDATED.
    # The pipeline is resumable from VALIDATED — it will run reconcile→policy→decide.
    if target == CaseStatus.EDITED:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            from apps.api.config import settings

            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await pool.enqueue_job("process_document", case.id)
            await pool.aclose()
        except Exception:
            logger.warning(
                "could not re-enqueue case %s after edit — manual reprocess needed", case_id
            )

    return ReviewResponse(
        case_id=case.id,
        new_status=case.status,
        action=body.action,
    )
