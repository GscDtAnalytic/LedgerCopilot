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

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, new_uuid


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    # dev | staging | production | None (archived)
    alias: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    system_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Scorecard JSON written by eval.run (null until evaluated)
    scorecard: Mapped[str | None] = mapped_column(Text, nullable=True)
