"""ModelRun — persists one AI gateway call.

Written after each gateway_call() completes. Best-effort: the pipeline never
blocks on this write, but it is how Phase 3 surfaces cost/latency dashboards
and lets scorecards be tied back to specific runs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, new_uuid


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    prompt_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(nullable=False, default=0.0)
    cost_usd: Mapped[float] = mapped_column(nullable=False, default=0.0)
    # PII-redacted prompt/completion. Null for stub runs.
    prompt_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
