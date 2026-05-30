"""add reference tables (suppliers, purchase_orders, payments, cost_centers)

Reference data that lets policy + reconciliation run against real records instead
of stubs: supplier registry/blocklist, PO totals, payments
(also serving as ledger entries), and the set of valid cost-center codes.

Revision ID: e7a1c2b3d4f5
Revises: c4d5e6f7a8b9
Create Date: 2026-05-29 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c2b3d4f5"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("tax_id_cnpj", sa.String(length=14), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("blocklisted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_org_cnpj", "suppliers", ["organization_id", "tax_id_cnpj"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("po_number", sa.String(length=64), nullable=False),
        sa.Column("supplier_cnpj", sa.String(length=14), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_orders_org_cnpj", "purchase_orders", ["organization_id", "supplier_cnpj"]
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("document_number", sa.String(length=128), nullable=False),
        sa.Column("supplier_cnpj", sa.String(length=14), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_org_docnum", "payments", ["organization_id", "document_number"])

    op.create_table(
        "cost_centers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_centers_org_code", "cost_centers", ["organization_id", "code"])


def downgrade() -> None:
    op.drop_index("ix_cost_centers_org_code", table_name="cost_centers")
    op.drop_table("cost_centers")
    op.drop_index("ix_payments_org_docnum", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_purchase_orders_org_cnpj", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_suppliers_org_cnpj", table_name="suppliers")
    op.drop_table("suppliers")
