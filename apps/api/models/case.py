"""Case — the processing unit that travels through the state machine."""

from __future__ import annotations

from packages.domain.state_machine import CaseStatus
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        # NOT unique — the same invoice may be retried; uniqueness is enforced
        # in the application by checking status (not rejected/received).
        Index("ix_cases_org_business_key", "organization_id", "business_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # Current status — transitions are validated by packages.domain.state_machine
    # before the DB write; every transition writes an immutable audit_event atomically.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=CaseStatus.RECEIVED)
    # document_type populated after CLASSIFIED stage
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Final decision: auto_approve | human_review | reject (populated at DECIDED)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Human-readable reason code (e.g. "clean_match", "value_mismatch+supplier_unknown")
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Risk score [0, 1] from the policy stage
    risk_score: Mapped[float | None] = mapped_column(nullable=True)
    # Version of the pipeline that processed this case
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    # Trace ID propagated across the pipeline for observability
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    # Short justification for the decision (written by the agent, analyst-language)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalized business key for dedup. Populated after extraction.
    # Format: cnpj:{14d}|doc:{doc}|total:{2dp}[|date:{date}]
    business_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
