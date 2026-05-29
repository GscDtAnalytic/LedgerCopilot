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
