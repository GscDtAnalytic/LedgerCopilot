"""Cost center reference data — feeds the "cost_center inválido" validation.

The set of active cost-center codes for an org is injected into the validation
engine as a ValidationContext; an extracted cost_center not in the set is a
blocking failure.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class CostCenter(Base, TimestampMixin):
    __tablename__ = "cost_centers"
    __table_args__ = (Index("ix_cost_centers_org_code", "organization_id", "code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
