"""PolicyDecision — persisted output of each policy rule evaluation.

One row per policy per case. Makes "which policies fired on this case" queryable
without parsing audit_event JSON.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class PolicyDecision(Base, TimestampMixin):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # pass | block | escalate
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_human: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True when an urgent-payment policy demands a second approver.
    requires_dual_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
