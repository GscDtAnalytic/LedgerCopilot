"""POST /api/v1/intake/email — email webhook intake (Phase 4).

Receives a parsed email payload and creates a Document + Case in the pipeline.
Requires authentication. The body content is sanitised before storing
.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user
from apps.api.database import get_session
from apps.api.models.audit import AuditEvent
from apps.api.models.case import Case
from apps.api.models.document import Document

router = APIRouter(prefix="/intake", tags=["intake"])

_MAX_BODY_LEN = 8_000
# Strip anything that looks like a prompt-injection attempt.
_INJECTION_RE = re.compile(
    r"\b(ignore (all )?(previous|prior|above) instructions?|"
    r"system prompt|forget (everything|all)|you are now)\b",
    re.IGNORECASE,
)


def _sanitise(text: str) -> str:
    cleaned = _INJECTION_RE.sub("[REDACTED]", text)
    return cleaned[:_MAX_BODY_LEN]


class EmailIntakeRequest(BaseModel):
    from_address: str
    subject: str
    body_text: str
    attachments: list[str] = []  # filenames; actual files via separate upload


class EmailIntakeResponse(BaseModel):
    case_id: str
    document_id: str
    message: str


@router.post("/email", response_model=EmailIntakeResponse, status_code=201)
async def intake_email(
    body: EmailIntakeRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> EmailIntakeResponse:
    """Create a Document + Case from an incoming email payload."""
    if not body.subject.strip():
        raise HTTPException(status_code=422, detail="subject must not be empty.")

    sanitised_body = _sanitise(body.body_text)
    trace_id = str(uuid.uuid4())

    # Deterministic hash of the email content so the same email doesn't
    # create two documents.
    email_content = f"{body.from_address}\0{body.subject}\0{body.body_text}"
    file_hash = hashlib.sha256(email_content.encode()).hexdigest()

    doc = Document(
        organization_id=user.org_id,
        original_filename=f"email:{body.subject[:120]}",
        file_hash=file_hash,
        content_type="message/rfc822",
        storage_path=f"email/{trace_id}",
        channel="email",
        file_size_bytes=len(sanitised_body.encode()),
    )
    session.add(doc)
    await session.flush()

    case = Case(
        organization_id=user.org_id,
        document_id=doc.id,
        trace_id=trace_id,
        status="received",
        pipeline_version="1.0.0",
    )
    session.add(case)
    await session.flush()

    audit = AuditEvent(
        case_id=case.id,
        organization_id=user.org_id,
        actor_type="human",
        actor_id=user.user_id,
        from_status="",
        to_status="received",
        trace_id=trace_id,
        payload={"channel": "email", "from": body.from_address, "subject": body.subject},
    )
    session.add(audit)
    await session.commit()

    return EmailIntakeResponse(
        case_id=case.id,
        document_id=doc.id,
        message="Email intake accepted. Case created and queued for processing.",
    )
