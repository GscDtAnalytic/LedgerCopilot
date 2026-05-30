"""Purchase order reference data — feeds reconciliation "document vs PO".

The reconciliation engine compares the extracted total against po_total; the
amount-delta policy uses the same number. Looked up by supplier CNPJ within an org.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (Index("ix_purchase_orders_org_cnpj", "organization_id", "supplier_cnpj"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    po_number: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)  # digits only
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
