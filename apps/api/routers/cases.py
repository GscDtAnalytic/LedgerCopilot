"""GET /api/v1/cases — inbox and case detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models import AuditEvent, Case, Document, ExtractionResult, ValidationResult
from apps.api.schemas.cases import (
    AuditEventOut,
    CaseDetail,
    CaseListItem,
    CasesListResponse,
    ExtractionFields,
    ValidationRule,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CasesListResponse)
async def list_cases(
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
) -> CasesListResponse:
    """Paginated case inbox ordered by creation date (newest first)."""
    offset = (page - 1) * page_size

    total = await session.scalar(select(func.count()).select_from(Case)) or 0

    rows = await session.execute(
        select(Case, Document)
        .join(Document, Case.document_id == Document.id)
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
) -> CaseDetail:
    """Full case detail including extracted fields and validation results."""
    case = await session.get(Case, case_id)
    if case is None:
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
) -> list[AuditEventOut]:
    """Immutable audit trail for a case, ordered chronologically."""
    case = await session.get(Case, case_id)
    if case is None:
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
