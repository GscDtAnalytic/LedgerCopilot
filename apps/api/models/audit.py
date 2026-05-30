"""AuditEvent — the immutable audit trail.

There is no case mutation without an event. Every state transition persists one
of these in the same DB transaction as the Case.status update. The table is
append-only; no row is ever updated or deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, new_uuid


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Who caused this transition
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # system|human|agent
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # user_id or agent name

    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)

    # Which prompt/policy drove this (None for system-level transitions)
    prompt_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Spans the entire pipeline run for this case
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # Arbitrary payload (evidence_refs, decision_branches, validation summary, etc.)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Written once at INSERT; never updated.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
