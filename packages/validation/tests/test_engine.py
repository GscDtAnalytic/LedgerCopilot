"""Tests for the deterministic validation engine — new rules (LC items / cost center)."""

from __future__ import annotations

from packages.domain.entities import ExtractionOutput, FieldValue, LineItem, ValidationRuleResult
from packages.validation.engine import ValidationContext, run_validations


def _base(total: float = 5000.0) -> ExtractionOutput:
    # 11.444.777/0001-61 is a checksum-valid CNPJ so cnpj_valid does not block —
    # isolating the rule under test (items / cost_center) from CNPJ validation.
    return ExtractionOutput(
        total_amount=FieldValue(value=total, confidence=0.9),
        tax_id_cnpj=FieldValue(value="11.444.777/0001-61", confidence=0.9),
        document_number=FieldValue(value="NF-001", confidence=0.9),
        currency=FieldValue(value="BRL", confidence=0.9),
    )


def _rule(results: list[ValidationRuleResult], name: str) -> ValidationRuleResult | None:
    return next((r for r in results if r.rule == name), None)


def test_items_sum_matches_total_passes() -> None:
    fields = _base(total=5000.0)
    fields.items = [
        LineItem(description="A", line_total=2000.0, confidence=0.8),
        LineItem(description="B", line_total=3000.0, confidence=0.8),
    ]
    results, has_block = run_validations(fields)
    rule = _rule(results, "items_sum_matches_total")
    assert rule is not None and rule.passed
    assert not has_block


def test_items_sum_mismatch_blocks() -> None:
    fields = _base(total=12000.0)
    fields.items = [
        LineItem(description="A", line_total=2000.0, confidence=0.8),
        LineItem(description="B", line_total=3000.0, confidence=0.8),
    ]
    results, has_block = run_validations(fields)
    rule = _rule(results, "items_sum_matches_total")
    assert rule is not None and not rule.passed and rule.severity == "block"
    assert has_block


def test_no_items_does_not_block() -> None:
    results, has_block = run_validations(_base())
    rule = _rule(results, "items_sum_matches_total")
    assert rule is not None and rule.passed
    assert not has_block


def test_cost_center_invalid_blocks_with_context() -> None:
    fields = _base()
    fields.cost_center = FieldValue(value="CC-999", confidence=0.8)
    ctx = ValidationContext(valid_cost_centers=frozenset({"CC-100", "CC-200"}))
    results, has_block = run_validations(fields, ctx)
    rule = _rule(results, "cost_center_valid")
    assert rule is not None and not rule.passed and rule.severity == "block"
    assert has_block


def test_cost_center_valid_passes_with_context() -> None:
    fields = _base()
    fields.cost_center = FieldValue(value="CC-100", confidence=0.8)
    ctx = ValidationContext(valid_cost_centers=frozenset({"CC-100", "CC-200"}))
    results, _ = run_validations(fields, ctx)
    rule = _rule(results, "cost_center_valid")
    assert rule is not None and rule.passed


def test_cost_center_without_context_is_warn_only() -> None:
    fields = _base()
    fields.cost_center = FieldValue(value="CC-999", confidence=0.8)
    # No context → engine cannot verify membership → must not block.
    _results, has_block = run_validations(fields)
    assert not has_block
