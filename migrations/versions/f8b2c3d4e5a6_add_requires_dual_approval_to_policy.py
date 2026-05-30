"""add requires_dual_approval to policy_decisions

Urgent-payment policy flags cases that need a second approver.
Persisted so the HITL UI and audit queries can surface it without parsing JSON.

Revision ID: f8b2c3d4e5a6
Revises: e7a1c2b3d4f5
Create Date: 2026-05-29 00:00:01.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8b2c3d4e5a6"
down_revision: str | None = "e7a1c2b3d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "policy_decisions",
        sa.Column(
            "requires_dual_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("policy_decisions", "requires_dual_approval")
