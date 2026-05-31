"""prompt_version_changelog

Adds a short changelog to prompt_versions so a version explains what changed vs the
one it derived from — closing the "registry of behaviour changes, not a CMS of text"
goal: based_on (parent version id), change_summary, expected_outcome.

All nullable; existing rows keep working. based_on is a free-form id (not an FK) so a
deleted parent never orphans a child's history.

Revision ID: b8e1d4072f5a
Revises: a7f3c1e9d204
Create Date: 2026-05-31 00:00:01.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e1d4072f5a"
down_revision: str | None = "a7f3c1e9d204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("based_on", sa.String(length=64), nullable=True))
    op.add_column("prompt_versions", sa.Column("change_summary", sa.String(length=512), nullable=True))
    op.add_column(
        "prompt_versions", sa.Column("expected_outcome", sa.String(length=512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("prompt_versions", "expected_outcome")
    op.drop_column("prompt_versions", "change_summary")
    op.drop_column("prompt_versions", "based_on")
