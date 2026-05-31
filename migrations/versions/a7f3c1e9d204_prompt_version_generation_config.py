"""prompt_version_generation_config

Adds per-version generation config to prompt_versions so a prompt version
carries the full configuration that affects agent behaviour (not just the
system text): model, temperature, top_p, max_tokens, and the Self-Consistency
fan-out k. These are wired through the worker and eval so a version's scorecard
reflects the version's actual config.

All columns are nullable. NULL means "use the standard default", so rows created
before this migration keep today's behaviour (temperature=1.0, max_tokens=512,
k=3, model=ai_gateway default). Coalescing happens in apps/api/services/prompts.

Revision ID: a7f3c1e9d204
Revises: 83ce92ede619
Create Date: 2026-05-31 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f3c1e9d204"
down_revision: str | None = "83ce92ede619"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("model", sa.String(length=64), nullable=True))
    op.add_column("prompt_versions", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("prompt_versions", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("prompt_versions", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("prompt_versions", sa.Column("k", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_versions", "k")
    op.drop_column("prompt_versions", "max_tokens")
    op.drop_column("prompt_versions", "top_p")
    op.drop_column("prompt_versions", "temperature")
    op.drop_column("prompt_versions", "model")
