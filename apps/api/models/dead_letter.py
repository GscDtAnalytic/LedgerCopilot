"""DeadLetter — cases that exhausted all pipeline retries.

Written in the same transaction as the failure audit_event. Cleared (resolved=True)
when an admin re-enqueues the case via POST /cases/{id}/reprocess.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class DeadLetter(Base, TimestampMixin):
    __tablename__ = "dead_letters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    error_type: Mapped[str] = mapped_column(String(256), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set to True when an admin re-enqueues the case for reprocessing.
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
