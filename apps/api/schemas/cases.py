"""Case-related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    case_id: str
    document_id: str
    trace_id: str
    status: str


class FieldValue(BaseModel):
    value: str | float | None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "ocr"


class LineItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    line_total: float | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ExtractionFields(BaseModel):
    supplier_name: FieldValue | None = None
    tax_id_cnpj: FieldValue | None = None
    total_amount: FieldValue | None = None
    currency: FieldValue | None = None
    issue_date: FieldValue | None = None
    due_date: FieldValue | None = None
    document_number: FieldValue | None = None
    cost_center: FieldValue | None = None
    category: FieldValue | None = None
    items: list[LineItem] = Field(default_factory=list)


class ValidationRule(BaseModel):
    rule: str
    passed: bool
    severity: str  # block | warn
    detail: str | None = None


class CaseListItem(BaseModel):
    id: str
    status: str
    document_type: str | None
    decision: str | None
    risk_score: float | None
    created_at: datetime
    original_filename: str


class CaseDetail(BaseModel):
    id: str
    status: str
    document_type: str | None
    decision: str | None
    reason_code: str | None
    risk_score: float | None
    justification: str | None
    trace_id: str
    pipeline_version: str
    created_at: datetime
    updated_at: datetime
    document_id: str
    original_filename: str
    file_hash: str
    channel: str
    extraction: ExtractionFields | None = None
    overall_confidence: float | None = None
    validations: list[ValidationRule] = Field(default_factory=list)
    has_blocking_failure: bool = False
    # True when a policy flagged this case as needing a second approver.
    requires_dual_approval: bool = False


class AuditEventOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None
    from_status: str
    to_status: str
    prompt_version_id: str | None
    model_name: str | None
    trace_id: str
    payload: dict
    occurred_at: datetime


class NarrativeResponse(BaseModel):
    case_id: str
    narrative: str


class CasesListResponse(BaseModel):
    items: list[CaseListItem]
    total: int
    page: int
    page_size: int


class ReviewRequest(BaseModel):
    action: str  # approve | reject | edit | request_context | resend_to_stage
    note: str | None = None
    # edited_fields: only required when action == "edit".
    # Keys are ExtractionOutput field names; values follow FieldValue schema.
    # Human-supplied values are trusted (confidence=1.0, source="human").
    edited_fields: dict[str, Any] | None = None
    # target_stage: required when action == "resend_to_stage" (extracted | validated).
    target_stage: str | None = None


class ReviewResponse(BaseModel):
    case_id: str
    new_status: str
    action: str


class ReprocessResponse(BaseModel):
    case_id: str
    enqueued: bool
    status: str
