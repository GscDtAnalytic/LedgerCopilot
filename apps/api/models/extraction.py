"""ExtractionResult — structured fields extracted from the document.

Every field carries a confidence score. Self-Consistency k=3 on critical fields
runs in the worker; confidence values stored here already reflect the consensus.
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
    # Serialized ExtractionOutput Pydantic model — LLM output is always validated
    # by the schema before use; this column never stores unvalidated raw JSON.
    fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Which prompt version produced this extraction
    prompt_version_id: Mapped[str] = mapped_column(String(64), nullable=False, default="dev-1.0")
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Overall extraction confidence (min of critical fields)
    overall_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    # Whether the sanitiser flagged a possible prompt-injection in the document text.
    # Persisted so a resumed pipeline (e.g. after a human edit) does not silently lose
    # the signal — context propagation.
    injection_suspected: Mapped[bool] = mapped_column(nullable=False, default=False)
