"""ValidationResult — deterministic rule engine output. No LLM involved.

Each rule is a pure function returning passed/failed and a severity.
A block-severity failure prevents auto_approve regardless of confidence.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class ValidationResult(Base, TimestampMixin):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # List of {"rule": str, "passed": bool, "severity": "block"|"warn", "detail": str|null}
    rules_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    has_blocking_failure: Mapped[bool] = mapped_column(nullable=False, default=False)
