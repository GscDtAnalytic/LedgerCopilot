"""POST /api/v1/documents — upload a financial document.

Creates Document + Case (RECEIVED) + first AuditEvent in a single transaction,
then enqueues the pipeline job. A duplicate file hash within the same org returns
the existing case rather than processing again.

Auth required: org_id is derived from the JWT, never hardcoded.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from packages.domain.enums import ActorType
from packages.domain.state_machine import CaseStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user
from apps.api.database import get_session
from apps.api.models import AuditEvent, Case, Document
from apps.api.schemas.cases import DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["documents"])

# Local storage path for dev; in prod this becomes a GCS/S3 upload.
_UPLOAD_DIR = Path("/tmp/ledgercopilot/uploads")


@router.post("", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Receive a financial document, create a traceable Case, enqueue processing."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    file_hash = hashlib.sha256(content).hexdigest()
    org_id = user.org_id

    # Dedup by hash within the same org — same file from different org is independent.
    existing_doc = await session.scalar(
        select(Document)
        .where(Document.file_hash == file_hash, Document.organization_id == org_id)
        .limit(1)
    )
    if existing_doc is not None:
        existing_case = await session.scalar(
            select(Case).where(Case.document_id == existing_doc.id).limit(1)
        )
        if existing_case is not None:
            return DocumentUploadResponse(
                case_id=existing_case.id,
                document_id=existing_doc.id,
                trace_id=existing_case.trace_id,
                status=existing_case.status,
            )

    # Store file locally (prod: upload to GCS/S3 here).
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{file_hash[:8]}_{file.filename or 'document'}"
    storage_path = str(_UPLOAD_DIR / stored_name)
    Path(storage_path).write_bytes(content)

    # --- Create Document + Case + AuditEvent in one transaction ---
    trace_id = str(uuid.uuid4())

    document = Document(
        organization_id=org_id,
        file_hash=file_hash,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        storage_path=storage_path,
        channel="upload",
        file_size_bytes=len(content),
    )
    session.add(document)
    await session.flush()

    case = Case(
        organization_id=org_id,
        document_id=document.id,
        status=CaseStatus.RECEIVED,
        trace_id=trace_id,
    )
    session.add(case)
    await session.flush()

    # First audit event: system created the case.
    audit = AuditEvent(
        case_id=case.id,
        organization_id=org_id,
        actor_type=ActorType.SYSTEM,
        actor_id="upload_endpoint",
        from_status="none",
        to_status=CaseStatus.RECEIVED,
        trace_id=trace_id,
        payload={"filename": document.original_filename, "file_hash": file_hash},
    )
    session.add(audit)
    await session.commit()

    # Enqueue pipeline job (fire and forget; worker picks it up via Redis).
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from apps.api.config import settings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.enqueue_job("process_document", case.id)
        await pool.aclose()
    except Exception:
        # If Redis is down we still return the case; the job can be re-enqueued.
        pass

    return DocumentUploadResponse(
        case_id=case.id,
        document_id=document.id,
        trace_id=trace_id,
        status=CaseStatus.RECEIVED,
    )
