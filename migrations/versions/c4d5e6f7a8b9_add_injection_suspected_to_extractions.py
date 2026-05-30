"""add_injection_suspected_to_extraction_results

Persists the injection_suspected signal on extraction_results so a resumed pipeline
(e.g. after a human edit sets the case back to VALIDATED) does not silently lose it.
Before this, the resume path defaulted the flag to False — a context-propagation gap
.

Revision ID: c4d5e6f7a8b9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-29 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extraction_results",
        sa.Column(
            "injection_suspected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("extraction_results", "injection_suspected")
