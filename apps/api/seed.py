"""Idempotent seed: default org, demo users, and reference data.

Demo credentials (all passwords: demo123):
  analyst@demo.com  — analyst role
  approver@demo.com — approver role
  admin@demo.com    — admin role
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import hash_password
from apps.api.models.cost_center import CostCenter
from apps.api.models.organization import Organization
from apps.api.models.payment import Payment
from apps.api.models.purchase_order import PurchaseOrder
from apps.api.models.supplier import Supplier
from apps.api.models.user import User

DEFAULT_ORG_ID = "default"
DEFAULT_ORG_SLUG = "default"

_DEMO_USERS = [
    {"id": "user-analyst", "email": "analyst@demo.com", "role": "analyst"},
    {"id": "user-approver", "email": "approver@demo.com", "role": "approver"},
    {"id": "user-admin", "email": "admin@demo.com", "role": "admin"},
]
_DEMO_PASSWORD = "demo123"

# Reference data for the demo. CNPJs are stored digits-only (lookup is normalised).
# "Acme Fornecedora" (12345678000190) matches the clean_invoice fixture so its case
# reconciles cleanly; "Blocked Supplier" exercises the hard-reject blocklist path.
_DEMO_SUPPLIERS = [
    {"cnpj": "12345678000190", "name": "Acme Fornecedora Ltda", "blocklisted": False},
    {"cnpj": "99888777000166", "name": "Blocked Supplier SA", "blocklisted": True},
    # Northwind has a VALID Mod-11 CNPJ (Acme's 12345678000190 does not), so a document
    # from Northwind that matches its PO can clear cnpj_valid and reach auto_approve. The
    # invalid-CNPJ Acme is kept on purpose to exercise the cnpj_valid blocking path.
    {"cnpj": "44555666000181", "name": "Northwind Traders Ltda", "blocklisted": False},
]
_DEMO_POS = [
    {"po_number": "PO-2024-0042", "supplier_cnpj": "12345678000190", "total_amount": 9500.0},
    # Under the 5000 auto-approve threshold — pair with a Northwind invoice of 4500 to
    # demonstrate a clean auto_approve end-to-end.
    {"po_number": "PO-2024-4500", "supplier_cnpj": "44555666000181", "total_amount": 4500.0},
]
_DEMO_PAYMENTS = [
    {"document_number": "NF-2024-00042", "supplier_cnpj": "12345678000190", "amount": 9500.0},
]
_DEMO_COST_CENTERS = [
    {"code": "CC-100", "name": "Operations", "active": True},
    {"code": "CC-200", "name": "Marketing", "active": True},
    {"code": "CC-900", "name": "Legacy (inactive)", "active": False},
]


async def ensure_default_org(session: AsyncSession) -> None:
    existing = await session.scalar(select(Organization).where(Organization.id == DEFAULT_ORG_ID))
    if existing is None:
        session.add(Organization(id=DEFAULT_ORG_ID, name="Default", slug=DEFAULT_ORG_SLUG))
        await session.commit()

    await _ensure_demo_users(session)
    await _ensure_reference_data(session)


async def _ensure_demo_users(session: AsyncSession) -> None:
    for u in _DEMO_USERS:
        existing = await session.scalar(select(User).where(User.email == u["email"]))
        if existing is None:
            session.add(
                User(
                    id=u["id"],
                    organization_id=DEFAULT_ORG_ID,
                    email=u["email"],
                    role=u["role"],
                    password_hash=hash_password(_DEMO_PASSWORD),
                )
            )
    await session.commit()


async def _ensure_reference_data(session: AsyncSession) -> None:
    """Idempotently seed suppliers / POs / payments / cost centers for the demo org."""
    for s in _DEMO_SUPPLIERS:
        exists = await session.scalar(
            select(Supplier).where(
                Supplier.organization_id == DEFAULT_ORG_ID,
                Supplier.tax_id_cnpj == s["cnpj"],
            )
        )
        if exists is None:
            session.add(
                Supplier(
                    organization_id=DEFAULT_ORG_ID,
                    tax_id_cnpj=s["cnpj"],
                    name=s["name"],
                    blocklisted=s["blocklisted"],
                )
            )

    for po in _DEMO_POS:
        exists = await session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.organization_id == DEFAULT_ORG_ID,
                PurchaseOrder.po_number == po["po_number"],
            )
        )
        if exists is None:
            session.add(PurchaseOrder(organization_id=DEFAULT_ORG_ID, **po))

    for pay in _DEMO_PAYMENTS:
        exists = await session.scalar(
            select(Payment).where(
                Payment.organization_id == DEFAULT_ORG_ID,
                Payment.document_number == pay["document_number"],
            )
        )
        if exists is None:
            session.add(Payment(organization_id=DEFAULT_ORG_ID, **pay))

    for cc in _DEMO_COST_CENTERS:
        exists = await session.scalar(
            select(CostCenter).where(
                CostCenter.organization_id == DEFAULT_ORG_ID,
                CostCenter.code == cc["code"],
            )
        )
        if exists is None:
            session.add(CostCenter(organization_id=DEFAULT_ORG_ID, **cc))

    await session.commit()
