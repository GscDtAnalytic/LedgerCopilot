"""Document — the uploaded file, hashed and stored.

Bronze layer: storage_path points to the immutable
original bytes. ocr_source / ocr_confidence capture how text was extracted
(wiki: — bronze should record provenance).
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 of the raw file bytes — used for dedup
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    # email | upload | api | bucket
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    file_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
    #: OCR provenance — set by the pipeline when text is extracted.
    # text | pdf-text | ocr-tesseract | ocr-image | ocr-failed | pdf-fallback
    ocr_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Average OCR engine confidence (0.0-1.0); null until pipeline runs.
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
