"""GET /api/v1/cases — inbox, case detail, audit trail, and audit-export (Phase 4).

Auth required: all queries scoped to user.org_id — no cross-tenant reads.
audit-export is gated to approver and admin roles.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user, require_roles
from apps.api.database import get_session
from apps.api.models import (
    AuditEvent,
    Case,
    DeadLetter,
    Document,
    ExtractionResult,
    ValidationResult,
)
from apps.api.schemas.cases import (
    AuditEventOut,
    CaseDetail,
    CaseListItem,
    CasesListResponse,
    ExtractionFields,
    ReprocessResponse,
    ValidationRule,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CasesListResponse)
async def list_cases(
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CasesListResponse:
    """Paginated case inbox for the authenticated user's org (newest first)."""
    offset = (page - 1) * page_size

    total = (
        await session.scalar(
            select(func.count()).select_from(Case).where(Case.organization_id == user.org_id)
        )
        or 0
    )

    rows = await session.execute(
        select(Case, Document)
        .join(Document, Case.document_id == Document.id)
        .where(Case.organization_id == user.org_id)
        .order_by(Case.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    items = [
        CaseListItem(
            id=case.id,
            status=case.status,
            document_type=case.document_type,
            decision=case.decision,
            risk_score=case.risk_score,
            created_at=case.created_at,
            original_filename=doc.original_filename,
        )
        for case, doc in rows
    ]

    return CasesListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(
    case_id: str,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CaseDetail:
    """Full case detail including extracted fields and validation results."""
    case = await session.get(Case, case_id)
    if case is None or case.organization_id != user.org_id:
        raise HTTPException(status_code=404, detail="Case not found.")

    doc = await session.get(Document, case.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    extraction = await session.scalar(
        select(ExtractionResult)
        .where(ExtractionResult.case_id == case_id)
        .order_by(ExtractionResult.created_at.desc())
        .limit(1)
    )

    validation = await session.scalar(
        select(ValidationResult)
        .where(ValidationResult.case_id == case_id)
        .order_by(ValidationResult.created_at.desc())
        .limit(1)
    )

    return CaseDetail(
        id=case.id,
        status=case.status,
        document_type=case.document_type,
        decision=case.decision,
        reason_code=case.reason_code,
        risk_score=case.risk_score,
        justification=case.justification,
        trace_id=case.trace_id,
        pipeline_version=case.pipeline_version,
        created_at=case.created_at,
        updated_at=case.updated_at,
        document_id=doc.id,
        original_filename=doc.original_filename,
        file_hash=doc.file_hash,
        channel=doc.channel,
        extraction=ExtractionFields(**extraction.fields_json) if extraction else None,
        overall_confidence=extraction.overall_confidence if extraction else None,
        validations=[ValidationRule(**r) for r in validation.rules_json] if validation else [],
        has_blocking_failure=validation.has_blocking_failure if validation else False,
    )


@router.get("/{case_id}/audit", response_model=list[AuditEventOut])
async def get_audit_trail(
    case_id: str,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> list[AuditEventOut]:
    """Immutable audit trail for a case, ordered chronologically."""
    case = await session.get(Case, case_id)
    if case is None or case.organization_id != user.org_id:
        raise HTTPException(status_code=404, detail="Case not found.")

    rows = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.occurred_at.asc())
    )

    return [
        AuditEventOut(
            id=ev.id,
            actor_type=ev.actor_type,
            actor_id=ev.actor_id,
            from_status=ev.from_status,
            to_status=ev.to_status,
            prompt_version_id=ev.prompt_version_id,
            model_name=ev.model_name,
            trace_id=ev.trace_id,
            payload=ev.payload,
            occurred_at=ev.occurred_at,
        )
        for (ev,) in rows
    ]


@router.get("/{case_id}/audit-export")
async def export_audit_package(
    case_id: str,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(require_roles("approver", "admin")),
) -> Response:
    """Download the full audit package (JSON). Gated to approver and admin."""
    case = await session.get(Case, case_id)
    if case is None or case.organization_id != user.org_id:
        raise HTTPException(status_code=404, detail="Case not found.")

    doc = await session.get(Document, case.document_id)

    extraction = await session.scalar(
        select(ExtractionResult)
        .where(ExtractionResult.case_id == case_id)
        .order_by(ExtractionResult.created_at.desc())
        .limit(1)
    )
    validation = await session.scalar(
        select(ValidationResult)
        .where(ValidationResult.case_id == case_id)
        .order_by(ValidationResult.created_at.desc())
        .limit(1)
    )
    audit_rows = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.occurred_at.asc())
    )

    package = {
        "export_version": "1.0",
        "case": {
            "id": case.id,
            "status": case.status,
            "decision": case.decision,
            "reason_code": case.reason_code,
            "risk_score": case.risk_score,
            "justification": case.justification,
            "trace_id": case.trace_id,
            "pipeline_version": case.pipeline_version,
            "created_at": case.created_at.isoformat(),
            "updated_at": case.updated_at.isoformat(),
        },
        "document": {
            "id": doc.id if doc else None,
            "original_filename": doc.original_filename if doc else None,
            "channel": doc.channel if doc else None,
            "file_hash": doc.file_hash if doc else None,
        },
        "extraction": extraction.fields_json if extraction else None,
        "validation": {
            "rules": validation.rules_json if validation else [],
            "has_blocking_failure": validation.has_blocking_failure if validation else False,
        },
        "audit_trail": [
            {
                "id": ev.id,
                "actor_type": ev.actor_type,
                "actor_id": ev.actor_id,
                "from_status": ev.from_status,
                "to_status": ev.to_status,
                "model_name": ev.model_name,
                "trace_id": ev.trace_id,
                "payload": ev.payload,
                "occurred_at": ev.occurred_at.isoformat(),
            }
            for (ev,) in audit_rows
        ],
    }

    return Response(
        content=json.dumps(package, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="audit_{case_id[:8]}.json"',
        },
    )


@router.post("/{case_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_case(
    case_id: str,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(require_roles("admin")),
) -> ReprocessResponse:
    """Re-enqueue a stuck or dead-lettered case for pipeline processing (admin only).

    Idempotent: the pipeline's resume logic skips stages already completed.
    Marks any open dead_letter entries as resolved and writes an audit_event.
    """
    case = await session.get(Case, case_id)
    if case is None or case.organization_id != user.org_id:
        raise HTTPException(status_code=404, detail="Case not found.")

    # Resolve open dead_letter entries for this case.
    dl_rows = await session.execute(
        select(DeadLetter).where(DeadLetter.case_id == case_id, DeadLetter.resolved.is_(False))
    )
    for (dl,) in dl_rows:
        dl.resolved = True

    # Audit: record the human reprocess decision.
    audit = AuditEvent(
        case_id=case_id,
        organization_id=case.organization_id,
        actor_type="human",
        actor_id=user.user_id,
        from_status=case.status,
        to_status=case.status,
        trace_id=case.trace_id,
        payload={"event": "admin_reprocess", "requester": user.email},
    )
    session.add(audit)
    await session.commit()

    # Re-enqueue via shared pool.
    try:
        from apps.api.redis_pool import get_redis_pool

        await get_redis_pool().enqueue_job("process_document", case_id)
        enqueued = True
    except Exception:
        enqueued = False

    return ReprocessResponse(case_id=case_id, enqueued=enqueued, status=case.status)
