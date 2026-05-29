"""ExtractionResult — structured fields extracted from the document.

Every field carries a confidence score. The Self-Consistency k=3 pass on critical
fields happens in the worker; by the time a result is persisted here the confidence
values already reflect the consensus.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class ExtractionResult(Base, TimestampMixin):
    __tablename__ = "extraction_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Serialized ExtractionOutput Pydantic model ( LLM output always
    # validated by a Pydantic schema before use; never raw JSON from the model).
    fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Which prompt version produced this extraction
    prompt_version_id: Mapped[str] = mapped_column(String(64), nullable=False, default="dev-1.0")
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Overall extraction confidence (min of critical fields)
    overall_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
