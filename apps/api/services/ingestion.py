"""Shared document ingestion.

Every channel (upload, email, csv, erp, bucket) converges here: hash → dedup →
store → Document + Case (RECEIVED) + first AuditEvent in one transaction. A single
path guarantees every channel gets the same traceability and hash-based deduplication.

Enqueuing the pipeline job is left to the caller because the Redis handle differs
by context (API request pool vs. arq worker context).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from packages.domain.enums import ActorType
from packages.domain.state_machine import CaseStatus
from packages.storage.factory import get_storage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models import AuditEvent, Case, Document

# Maps common field aliases (en/pt) to the labelled lines our extractor recognises,
# so structured channels (CSV/XLSX/ERP) flow through the same OCR→extract pipeline.
_LABEL_BY_KEY: dict[str, str] = {
    "supplier_name": "Fornecedor",
    "supplier": "Fornecedor",
    "fornecedor": "Fornecedor",
    "emitente": "Fornecedor",
    "tax_id_cnpj": "CNPJ",
    "cnpj": "CNPJ",
    "tax_id": "CNPJ",
    "total_amount": "Total",
    "total": "Total",
    "valor_total": "Total",
    "amount": "Total",
    "currency": "Moeda",
    "moeda": "Moeda",
    "issue_date": "Data de Emissao",
    "emissao": "Data de Emissao",
    "data_emissao": "Data de Emissao",
    "due_date": "Data de Vencimento",
    "vencimento": "Data de Vencimento",
    "document_number": "Numero",
    "numero": "Numero",
    "nf": "Numero",
    "invoice_number": "Numero",
    "cost_center": "Centro de Custo",
    "centro_custo": "Centro de Custo",
    "category": "Categoria",
    "categoria": "Categoria",
}


@dataclass(frozen=True)
class IngestResult:
    case_id: str
    document_id: str
    trace_id: str
    status: str
    is_duplicate: bool


def canonical_text_from_mapping(data: dict[str, object]) -> str:
    """Serialise a structured record (CSV row / ERP payload) into labelled text.

    Known keys are mapped to Portuguese labels the extractor understands; unknown
    keys are passed through verbatim so no information is silently dropped.
    """
    lines: list[str] = []
    for raw_key, value in data.items():
        if value is None or str(value).strip() == "":
            continue
        key = str(raw_key).strip().lower().replace(" ", "_")
        label = _LABEL_BY_KEY.get(key, str(raw_key).strip())
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


async def ingest_document(
    session: AsyncSession,
    org_id: str,
    *,
    filename: str,
    content_type: str,
    content: bytes,
    channel: str,
    actor_type: ActorType = ActorType.SYSTEM,
    actor_id: str = "ingest",
    existing_storage_path: str | None = None,
    extra_payload: dict | None = None,
) -> IngestResult:
    """Create Document + Case + first AuditEvent, deduplicating by content hash.

    Returns an IngestResult; when the file hash already exists for the org the
    existing case is returned with is_duplicate=True and nothing new is written.
    The caller is responsible for enqueuing the pipeline job for non-duplicates.
    """
    file_hash = hashlib.sha256(content).hexdigest()

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
            return IngestResult(
                case_id=existing_case.id,
                document_id=existing_doc.id,
                trace_id=existing_case.trace_id,
                status=existing_case.status,
                is_duplicate=True,
            )

    if existing_storage_path is not None:
        storage_path = existing_storage_path
    else:
        stored_name = f"{file_hash[:8]}_{filename}"
        storage = get_storage(settings.storage_backend, settings.storage_local_dir)
        storage_path = storage.put(stored_name, content)

    trace_id = str(uuid.uuid4())
    document = Document(
        organization_id=org_id,
        file_hash=file_hash,
        original_filename=filename,
        content_type=content_type,
        storage_path=storage_path,
        channel=channel,
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

    payload = {"filename": filename, "file_hash": file_hash, "channel": channel}
    if extra_payload:
        payload.update(extra_payload)
    session.add(
        AuditEvent(
            case_id=case.id,
            organization_id=org_id,
            actor_type=actor_type,
            actor_id=actor_id,
            from_status="none",
            to_status=CaseStatus.RECEIVED,
            trace_id=trace_id,
            payload=payload,
        )
    )
    await session.commit()

    return IngestResult(
        case_id=case.id,
        document_id=document.id,
        trace_id=trace_id,
        status=CaseStatus.RECEIVED,
        is_duplicate=False,
    )
