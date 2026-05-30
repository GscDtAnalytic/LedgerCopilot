"""Tests for the deterministic policy engine."""

from __future__ import annotations

from packages.domain.entities import ExtractionOutput, FieldValue
from packages.policy.engine import run_policy


def _fields(confidence: float = 0.95, total: float | None = 1000.0) -> ExtractionOutput:
    return ExtractionOutput(
        total_amount=FieldValue(value=total, confidence=confidence) if total else None,
        tax_id_cnpj=FieldValue(value="12.345.678/0001-90", confidence=confidence),
        document_number=FieldValue(value="NF-001", confidence=confidence),
    )


def test_high_confidence_registered_passes() -> None:
    _, risk, requires_human = run_policy(
        fields=_fields(confidence=0.95),
        has_blocking_failure=False,
        supplier_registered=True,
        po_total=1000.0,
    )
    assert not requires_human
    assert risk < 0.5


def test_blocking_failure_always_requires_human() -> None:
    _, risk, requires_human = run_policy(
        fields=_fields(confidence=0.95),
        has_blocking_failure=True,
        supplier_registered=True,
        po_total=1000.0,
    )
    assert requires_human
    assert risk >= 0.5


def test_unknown_supplier_requires_human() -> None:
    _, _, requires_human = run_policy(
        fields=_fields(confidence=0.95),
        has_blocking_failure=False,
        supplier_registered=False,
    )
    assert requires_human


def test_low_confidence_requires_human() -> None:
    _, _, requires_human = run_policy(
        fields=_fields(confidence=0.40),
        has_blocking_failure=False,
        supplier_registered=True,
    )
    assert requires_human


def test_amount_delta_over_threshold_requires_human() -> None:
    # Extracted 1000, PO says 800 → 25% delta > 10% threshold
    _, _, requires_human = run_policy(
        fields=_fields(confidence=0.95, total=1000.0),
        has_blocking_failure=False,
        supplier_registered=True,
        po_total=800.0,
    )
    assert requires_human


def test_risk_score_capped_at_one() -> None:
    _, risk, _ = run_policy(
        fields=_fields(confidence=0.10),
        has_blocking_failure=True,
        supplier_registered=False,
        po_total=1.0,
    )
    assert risk <= 1.0


def test_amount_over_auto_approve_limit_requires_human() -> None:
    # Total 12000 above the 5000 auto-approve limit → never auto-approve (§9).
    decisions, _, requires_human = run_policy(
        fields=_fields(confidence=0.95, total=12000.0),
        has_blocking_failure=False,
        supplier_registered=True,
        po_total=12000.0,
    )
    assert requires_human
    assert any(d.policy_id == "p-amount-threshold" for d in decisions)


def test_amount_under_custom_limit_does_not_escalate() -> None:
    # With a higher org limit the same amount clears the threshold policy.
    decisions, _, _ = run_policy(
        fields=_fields(confidence=0.95, total=12000.0),
        has_blocking_failure=False,
        supplier_registered=True,
        po_total=12000.0,
        amount_limit=50000.0,
    )
    assert any(d.policy_id == "p-amount-under-limit" for d in decisions)


def test_category_requiring_justification_escalates() -> None:
    fields = _fields(confidence=0.95)
    fields.category = FieldValue(value="legal", confidence=0.9)
    decisions, _, requires_human = run_policy(
        fields=fields,
        has_blocking_failure=False,
        supplier_registered=True,
        justification_present=False,
    )
    assert requires_human
    assert any(d.policy_id == "p-category-justification" for d in decisions)


def test_category_with_justification_passes() -> None:
    fields = _fields(confidence=0.95)
    fields.category = FieldValue(value="legal", confidence=0.9)
    decisions, _, _ = run_policy(
        fields=fields,
        has_blocking_failure=False,
        supplier_registered=True,
        justification_present=True,
    )
    assert any(d.policy_id == "p-category-ok" for d in decisions)


def test_urgent_payment_requires_dual_approval() -> None:
    fields = _fields(confidence=0.95)
    fields.issue_date = FieldValue(value="2024-03-15", confidence=0.9)
    fields.due_date = FieldValue(value="2024-03-17", confidence=0.9)  # 2 days
    decisions, _, requires_human = run_policy(
        fields=fields,
        has_blocking_failure=False,
        supplier_registered=True,
    )
    assert requires_human
    urgent = [d for d in decisions if d.policy_id == "p-urgent-payment"]
    assert urgent and urgent[0].requires_dual_approval


def test_non_urgent_payment_no_dual_approval() -> None:
    fields = _fields(confidence=0.95)
    fields.issue_date = FieldValue(value="2024-03-15", confidence=0.9)
    fields.due_date = FieldValue(value="2024-04-15", confidence=0.9)  # 31 days
    decisions, _, _ = run_policy(
        fields=fields,
        has_blocking_failure=False,
        supplier_registered=True,
    )
    assert not any(getattr(d, "requires_dual_approval", False) for d in decisions)
