"""PromptVersion — DB-backed versioned prompt registry.

Each row is a prompt version promotable through aliases: dev → staging → production.
Only one row per alias is active at a time. The DB record is the source of truth
for what prompt ran in production; the in-process registry (packages/ai_gateway/
registry.py) is used as a fallback when the DB is not reachable.

Promotion to production requires a passing eval scorecard (enforced in the promote
endpoint, not here).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, new_uuid


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    # dev | staging | production | None (archived)
    alias: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    system_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Scorecard JSON written by eval.run (null until evaluated)
    scorecard: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-version generation config (wired through worker + eval).
    # All nullable: NULL means "use the standard default" so pre-existing rows keep
    # today's behaviour. Consumers coalesce via apps/api/services/prompts.
    #   model=NULL        → ai_gateway default (AI_DEFAULT_MODEL)
    #   temperature=NULL  → 1.0   (standard Self-Consistency sampling)
    #   top_p=NULL        → unset (provider default)
    #   max_tokens=NULL   → 512
    #   k=NULL            → 3     (Self-Consistency fan-out)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    k: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Changelog — what changed vs the parent version, for analytical governance.
    # based_on points at the version this one was cloned/derived from (free-form id,
    # not an FK, so deleting a parent never orphans the child's history).
    based_on: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_outcome: Mapped[str | None] = mapped_column(String(512), nullable=True)
