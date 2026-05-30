"""Supplier registry — reference data for policy + reconciliation.

Lets the pipeline answer two questions deterministically at the I/O boundary:
  - is this supplier registered? (p-supplier-unknown policy)
  - is this supplier blocklisted? (hard reject in reconciliation)

Looked up by CNPJ within an organization. Pure engines never touch this table —
apps/api/services/reference.py reads it and injects the result.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_org_cnpj", "organization_id", "tax_id_cnpj"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Stored normalised (digits only) so lookups are punctuation-insensitive.
    tax_id_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    blocklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
