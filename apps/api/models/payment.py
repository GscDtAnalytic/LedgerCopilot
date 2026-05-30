"""Payment / ledger entry reference data.

A payment is a recorded money movement — it serves both the "document vs payment"
and "document vs lançamento (ledger entry)" reconciliation checks. Matched to a
document by document_number within an organization.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_org_docnum", "organization_id", "document_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    document_number: Mapped[str] = mapped_column(String(128), nullable=False)
    supplier_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
