"""User — belongs to an Organization, carries a role (analyst | approver | admin)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin, new_uuid


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="analyst")
    password_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
