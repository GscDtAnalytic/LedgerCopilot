"""Tests for the reconciliation engine — pure, no fixtures needed.

Covers the two mandatory eval slices: value_mismatch and duplicate_invoice.
"""

from __future__ import annotations

from packages.domain.decisions import decide
from packages.domain.entities import ExtractionOutput, FieldValue
from packages.domain.enums import Decision
from packages.reconciliation.engine import ReconciliationContext, reconcile


def _fields(total: float = 1000.0, confidence: float = 0.95) -> ExtractionOutput:
    return ExtractionOutput(
        total_amount=FieldValue(value=total, confidence=confidence),
        tax_id_cnpj=FieldValue(value="12.345.678/0001-90", confidence=confidence),
        document_number=FieldValue(value="NF-001", confidence=confidence),
    )


# ── Hard reject tier ──────────────────────────────────────────────────────────


def test_supplier_blocklisted_rejects() -> None:
    ctx = ReconciliationContext(supplier_blocklisted=True)
    result = reconcile(_fields(), ctx)
    assert result.reject_reason == "supplier_blocklisted"
    assert result.risk_delta == 1.0
    assert not result.matched
    assert result.deltas == []


def test_duplicate_invoice_rejects() -> None:
    ctx = ReconciliationContext(business_key_seen=True)
    result = reconcile(_fields(), ctx)
    assert result.reject_reason == "duplicate_invoice"
    assert result.risk_delta == 1.0
    assert not result.matched


def test_blocklist_takes_priority_over_business_key() -> None:
    # Both flags set — blocklist wins (returns first).
    ctx = ReconciliationContext(supplier_blocklisted=True, business_key_seen=True)
    result = reconcile(_fields(), ctx)
    assert result.reject_reason == "supplier_blocklisted"


# ── Soft mismatch tier ────────────────────────────────────────────────────────


def test_value_mismatch_vs_po_not_matched() -> None:
    # Extracted 1200, PO 1000 → 20% delta > 10% threshold.
    ctx = ReconciliationContext(po_total=1000.0)
    result = reconcile(_fields(total=1200.0), ctx)
    assert not result.matched
    assert result.reject_reason is None
    assert len(result.deltas) == 1
    assert result.deltas[0].field == "total_amount"
    assert result.risk_delta > 0.0


def test_value_mismatch_vs_payment_not_matched() -> None:
    # Extracted 1100, payment 1000 → 10% delta > 5% threshold.
    ctx = ReconciliationContext(payment_total=1000.0)
    result = reconcile(_fields(total=1100.0), ctx)
    assert not result.matched
    assert result.reject_reason is None
    assert len(result.deltas) == 1


def test_value_within_po_threshold_matches() -> None:
    # Extracted 1050, PO 1000 → 5% delta ≤ 10% threshold.
    ctx = ReconciliationContext(po_total=1000.0)
    result = reconcile(_fields(total=1050.0), ctx)
    assert result.matched
    assert result.deltas == []
    assert result.risk_delta == 0.0


def test_clean_invoice_no_context_matches() -> None:
    ctx = ReconciliationContext()
    result = reconcile(_fields(), ctx)
    assert result.matched
    assert result.risk_delta == 0.0
    assert result.reject_reason is None


def test_risk_delta_capped_at_point_seven() -> None:
    # Two deltas simultaneously (PO + payment) → risk capped at 0.7.
    ctx = ReconciliationContext(po_total=1000.0, payment_total=900.0)
    result = reconcile(_fields(total=1500.0), ctx)
    assert result.risk_delta <= 0.7


# ── Integration: decide() with recon_reject_reason ────────────────────────────


def test_decide_rejects_on_duplicate_invoice() -> None:
    fields = _fields()
    ctx = ReconciliationContext(business_key_seen=True)
    recon_out = reconcile(fields, ctx)

    decision, reason_code, _, _ = decide(
        fields,
        has_blocking_failure=False,
        risk_score=1.0,
        requires_human=False,
        recon_reject_reason=recon_out.reject_reason,
    )
    assert decision == Decision.REJECT
    assert reason_code == "duplicate_invoice"


def test_decide_rejects_on_blocklist_even_if_policy_requires_human() -> None:
    fields = _fields()
    ctx = ReconciliationContext(supplier_blocklisted=True)
    recon_out = reconcile(fields, ctx)

    # Policy also set requires_human (as it might for unknown supplier), but
    # the hard recon block overrides to REJECT.
    decision, reason_code, _, _ = decide(
        fields,
        has_blocking_failure=False,
        risk_score=1.0,
        requires_human=True,  # policy escalation present
        recon_reject_reason=recon_out.reject_reason,
    )
    assert decision == Decision.REJECT
    assert reason_code == "supplier_blocklisted"


def test_decide_human_review_on_value_mismatch() -> None:
    fields = _fields(total=1300.0)
    ctx = ReconciliationContext(po_total=1000.0)
    recon_out = reconcile(fields, ctx)

    # Soft mismatch: pipeline sets requires_human=True when matched=False and no hard reject.
    # Mirrors the pipeline S5 logic: soft mismatch escalates to review.
    requires_human = not recon_out.matched and not recon_out.reject_reason
    risk_policy = 0.3

    decision, _reason_code, _, _ = decide(
        fields,
        has_blocking_failure=False,
        risk_score=risk_policy + recon_out.risk_delta,
        requires_human=requires_human,
        recon_reject_reason=recon_out.reject_reason,
    )
    assert decision == Decision.HUMAN_REVIEW
    assert recon_out.reject_reason is None
