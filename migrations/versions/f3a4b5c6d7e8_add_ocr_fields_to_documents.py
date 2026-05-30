"""add_ocr_fields_to_documents

Adds ocr_source and ocr_confidence to the documents table (bronze layer metadata).
Merges the two open heads (b2c3d4e5f6a7, dc75a14b152f).

Revision ID: f3a4b5c6d7e8
Revises: b2c3d4e5f6a7, dc75a14b152f
Create Date: 2026-05-29 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: tuple[str, str] = ("b2c3d4e5f6a7", "dc75a14b152f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ocr_source", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("ocr_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "ocr_confidence")
    op.drop_column("documents", "ocr_source")
