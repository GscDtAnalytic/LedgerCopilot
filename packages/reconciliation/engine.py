"""Reconciliation engine — pure, no I/O.

Reconciles extracted fields against purchase orders, payments, and history.
The context (PO total, payment total, duplicate flag, blocklist flag) is fetched
at the I/O boundary and injected here; this module never touches a DB or network.

Two outcome tiers:
  - Hard reject (reject_reason set): duplicate invoice confirmed or supplier
    blocklisted — deterministic, no human second-guessing.
  - Soft mismatch (deltas, risk_delta > 0, matched=False): amount deviates from
    PO/payment beyond threshold — escalates to human_review with explanation.
  - Clean match: matched=True, risk_delta=0.0.

Wiki: (dedup → reject);
(reconciliar pós-extração; consistência entre sistemas).
"""

from __future__ import annotations

from pydantic import BaseModel

from packages.domain.entities import ExtractionOutput

_AMOUNT_DELTA_THRESHOLD = 0.10  # 10% — escalate to review
_PAYMENT_DELTA_THRESHOLD = 0.05  # 5% — tighter: already paid


class ReconciliationContext(BaseModel):
    """External context injected by the pipeline (fetched at I/O boundary)."""

    po_total: float | None = None
    payment_total: float | None = None
    # True when another non-rejected case with the same business key already exists.
    # Detection logic lives in (business key dedup); the pipeline passes
    # the result here so the engine remains pure.
    business_key_seen: bool = False
    supplier_blocklisted: bool = False


class ReconciliationDelta(BaseModel):
    """A single discrepancy between extracted data and expected context."""

    field: str
    extracted: float | str | None
    expected: float | str | None
    delta_pct: float | None = None
    reason: str


class ReconciliationOutput(BaseModel):
    """Result of reconcile(). Persisted as reconciliation_result row."""

    matched: bool
    deltas: list[ReconciliationDelta]
    risk_delta: float  # additive; 1.0 = hard reject, flows into overall risk_score
    reject_reason: str | None = None  # set only for deterministic rejects


def reconcile(fields: ExtractionOutput, context: ReconciliationContext) -> ReconciliationOutput:
    """Reconcile extracted fields against the injected context.

    Determinism: every branch is a pure function of `fields` and `context`.
    No LLM call, no randomness.
    """
    deltas: list[ReconciliationDelta] = []

    # ── Hard reject tier ─────────────────────────────────────────────────────
    # Supplier on blocklist — never proceed, no human review needed.
    if context.supplier_blocklisted:
        return ReconciliationOutput(
            matched=False,
            deltas=[],
            risk_delta=1.0,
            reject_reason="supplier_blocklisted",
        )

    # Confirmed business-key duplicate: same CNPJ+number+amount+date already
    # exists in a non-rejected terminal case.
    if context.business_key_seen:
        return ReconciliationOutput(
            matched=False,
            deltas=[],
            risk_delta=1.0,
            reject_reason="duplicate_invoice",
        )

    # ── Soft mismatch tier ───────────────────────────────────────────────────
    extracted_total: float | None = None
    if fields.total_amount and isinstance(fields.total_amount.value, float | int):
        extracted_total = float(fields.total_amount.value)

    # PO amount delta
    if context.po_total is not None and extracted_total is not None:
        delta = abs(extracted_total - context.po_total) / (context.po_total + 1e-9)
        if delta > _AMOUNT_DELTA_THRESHOLD:
            deltas.append(
                ReconciliationDelta(
                    field="total_amount",
                    extracted=extracted_total,
                    expected=context.po_total,
                    delta_pct=round(delta, 4),
                    reason=(
                        f"amount_delta={delta:.1%} > {_AMOUNT_DELTA_THRESHOLD:.0%} threshold vs PO"
                    ),
                )
            )

    # Payment amount delta (tighter threshold — the money already moved)
    if context.payment_total is not None and extracted_total is not None:
        delta = abs(extracted_total - context.payment_total) / (context.payment_total + 1e-9)
        if delta > _PAYMENT_DELTA_THRESHOLD:
            deltas.append(
                ReconciliationDelta(
                    field="total_amount",
                    extracted=extracted_total,
                    expected=context.payment_total,
                    delta_pct=round(delta, 4),
                    reason=(
                        f"amount_delta={delta:.1%} > {_PAYMENT_DELTA_THRESHOLD:.0%}"
                        " threshold vs payment"
                    ),
                )
            )

    if deltas:
        # Each delta adds 0.35 risk; cap contribution from this stage at 0.7.
        risk_delta = min(0.7, len(deltas) * 0.35)
        return ReconciliationOutput(
            matched=False,
            deltas=deltas,
            risk_delta=risk_delta,
            reject_reason=None,
        )

    return ReconciliationOutput(matched=True, deltas=[], risk_delta=0.0)
