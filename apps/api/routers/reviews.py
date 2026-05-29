"""POST /api/v1/cases/{id}/review — human reviewer actions.

Supports three actions:
  - approve → IN_HUMAN_REVIEW → APPROVED → CLOSED
  - reject  → IN_HUMAN_REVIEW → REJECTED → CLOSED
  - edit    → IN_HUMAN_REVIEW → EDITED → (back to VALIDATED, re-enters pipeline)

Every action writes a HumanReview row + AuditEvent in the same DB transaction
as the Case.status change. Reviewer identity flows in via the request body for
now; Phase 4 replaces this with JWT auth and RBAC.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from packages.domain.enums import ActorType
from packages.domain.state_machine import (
    CaseStatus,
    InvalidTransitionError,
    assert_transition,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models import AuditEvent, Case, HumanReview
from apps.api.schemas.cases import ReviewRequest, ReviewResponse

router = APIRouter(prefix="/cases", tags=["reviews"])

_ACTION_TO_STATUS: dict[str, CaseStatus] = {
    "approve": CaseStatus.APPROVED,
    "reject": CaseStatus.REJECTED,
    "edit": CaseStatus.EDITED,
}

_TERMINAL_AFTER: dict[CaseStatus, CaseStatus | None] = {
    CaseStatus.APPROVED: CaseStatus.CLOSED,
    CaseStatus.REJECTED: CaseStatus.CLOSED,
    CaseStatus.EDITED: None,  # edited re-enters the pipeline at VALIDATED
}


@router.post("/{case_id}/review", response_model=ReviewResponse)
async def review_case(
    case_id: str,
    body: ReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> ReviewResponse:
    """Apply a human review action. Atomic: status + HumanReview + AuditEvent."""
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    if body.action not in _ACTION_TO_STATUS:
        raise HTTPException(
            status_code=422,
            detail=f"action must be one of: {list(_ACTION_TO_STATUS)}",
        )

    target = _ACTION_TO_STATUS[body.action]

    # Validate the transition before touching the DB.
    try:
        assert_transition(CaseStatus(case.status), target)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # --- Atomic write: HumanReview + Case.status + AuditEvent ---
    review = HumanReview(
        case_id=case.id,
        reviewer_id=body.reviewer_id,
        action=body.action,
        note=body.note,
    )
    session.add(review)

    audit = AuditEvent(
        case_id=case.id,
        organization_id=case.organization_id,
        actor_type=ActorType.HUMAN,
        actor_id=body.reviewer_id,
        from_status=case.status,
        to_status=target,
        trace_id=case.trace_id,
        payload={"action": body.action, "note": body.note or ""},
    )
    case.status = target
    session.add(audit)
    await session.flush()

    # If this action has a natural terminal follow-on, apply it now.
    terminal = _TERMINAL_AFTER.get(target)
    if terminal is not None:
        terminal_audit = AuditEvent(
            case_id=case.id,
            organization_id=case.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id="review_endpoint",
            from_status=target,
            to_status=terminal,
            trace_id=case.trace_id,
            payload={"reason": "auto-closed after human decision"},
        )
        case.status = terminal
        session.add(terminal_audit)
        await session.flush()

    await session.commit()

    return ReviewResponse(
        case_id=case.id,
        new_status=case.status,
        action=body.action,
    )
