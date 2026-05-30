"""Reference-data lookups at the I/O boundary.

The pure engines (validation, policy, reconciliation) must never touch the DB.
This service reads the reference tables (suppliers, purchase_orders, payments,
cost_centers) and returns plain values the pipeline injects into the engines'
*Context objects. Lookups are org-scoped and CNPJ-insensitive to punctuation.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.domain.business_key import normalise_cnpj
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import CostCenter, Payment, PurchaseOrder, Supplier


@dataclass(frozen=True)
class SupplierInfo:
    registered: bool
    blocklisted: bool


async def lookup_supplier(session: AsyncSession, org_id: str, cnpj: str | None) -> SupplierInfo:
    """Resolve supplier registration + blocklist status by CNPJ.

    Unknown CNPJ → registered=False (forces no-auto-approve via policy). A missing
    CNPJ is treated as unregistered, never as "trusted".
    """
    digits = normalise_cnpj(cnpj)
    if digits is None:
        return SupplierInfo(registered=False, blocklisted=False)
    row = await session.scalar(
        select(Supplier).where(Supplier.organization_id == org_id, Supplier.tax_id_cnpj == digits)
    )
    if row is None:
        return SupplierInfo(registered=False, blocklisted=False)
    return SupplierInfo(registered=True, blocklisted=row.blocklisted)


async def lookup_po_total(session: AsyncSession, org_id: str, cnpj: str | None) -> float | None:
    """Return the PO total for this supplier, or None when no PO exists."""
    digits = normalise_cnpj(cnpj)
    if digits is None:
        return None
    row = await session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == org_id,
            PurchaseOrder.supplier_cnpj == digits,
        )
    )
    return row.total_amount if row is not None else None


async def lookup_payment_total(
    session: AsyncSession, org_id: str, document_number: str | None
) -> float | None:
    """Return the recorded payment/ledger amount for this document, or None."""
    if not document_number:
        return None
    row = await session.scalar(
        select(Payment).where(
            Payment.organization_id == org_id,
            Payment.document_number == str(document_number).strip(),
        )
    )
    return row.amount if row is not None else None


async def active_cost_center_codes(session: AsyncSession, org_id: str) -> frozenset[str]:
    """Return the set of active cost-center codes for the org (empty if none seeded)."""
    rows = await session.scalars(
        select(CostCenter.code).where(
            CostCenter.organization_id == org_id, CostCenter.active.is_(True)
        )
    )
    return frozenset(rows.all())
