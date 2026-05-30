"""ReconciliationResult — persisted output of the reconciliation engine.

Materialises what was previously only in the audit_event payload, making it
directly queryable without JSON parsing.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class ReconciliationResult(Base, TimestampMixin):
    __tablename__ = "reconciliation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deltas_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Non-null only for hard-reject outcomes (duplicate_invoice, supplier_blocklisted).
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
