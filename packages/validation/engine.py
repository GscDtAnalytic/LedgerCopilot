"""Deterministic validation engine.

Rules are pure functions: receive data, return result + reason. No LLM, no I/O.
A rule that returns severity="block" prevents auto_approve regardless of confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from packages.domain.entities import ExtractionOutput, ValidationRuleResult


@dataclass(frozen=True)
class RuleResult:
    rule: str
    passed: bool
    severity: str  # block | warn
    detail: str | None = None

    def to_schema(self) -> ValidationRuleResult:
        return ValidationRuleResult(
            rule=self.rule,
            passed=self.passed,
            severity=self.severity,
            detail=self.detail,
        )


def _rule_amount_non_negative(fields: ExtractionOutput) -> RuleResult:
    fv = fields.total_amount
    if fv is None or fv.value is None:
        return RuleResult("amount_present", False, "block", "total_amount is missing")
    try:
        if float(fv.value) < 0:
            return RuleResult("amount_non_negative", False, "block", f"amount={fv.value}")
    except (TypeError, ValueError):
        return RuleResult("amount_non_negative", False, "block", "amount is not numeric")
    return RuleResult("amount_non_negative", True, "block")


def _rule_cnpj_present(fields: ExtractionOutput) -> RuleResult:
    fv = fields.tax_id_cnpj
    if fv is None or not fv.value:
        return RuleResult("cnpj_present", False, "block", "tax_id_cnpj is missing")
    return RuleResult("cnpj_present", True, "block")


def _rule_cnpj_format(fields: ExtractionOutput) -> RuleResult:
    fv = fields.tax_id_cnpj
    if fv is None or not fv.value:
        return RuleResult("cnpj_format", False, "warn", "no CNPJ to validate")
    digits = re.sub(r"\D", "", str(fv.value))
    if len(digits) != 14:
        return RuleResult("cnpj_format", False, "block", f"expected 14 digits, got {len(digits)}")
    return RuleResult("cnpj_format", True, "block")


def _rule_currency_present(fields: ExtractionOutput) -> RuleResult:
    fv = fields.currency
    if fv is None or not fv.value:
        return RuleResult("currency_present", False, "warn", "currency not extracted")
    return RuleResult("currency_present", True, "warn")


def _rule_document_number_present(fields: ExtractionOutput) -> RuleResult:
    fv = fields.document_number
    if fv is None or not fv.value:
        return RuleResult("document_number_present", False, "warn", "document_number missing")
    return RuleResult("document_number_present", True, "warn")


def _rule_supplier_name_present(fields: ExtractionOutput) -> RuleResult:
    fv = fields.supplier_name
    if fv is None or not fv.value:
        return RuleResult("supplier_name_present", False, "warn", "supplier_name not extracted")
    return RuleResult("supplier_name_present", True, "warn")


_RULES = [
    _rule_amount_non_negative,
    _rule_cnpj_present,
    _rule_cnpj_format,
    _rule_currency_present,
    _rule_document_number_present,
    _rule_supplier_name_present,
]


def run_validations(fields: ExtractionOutput) -> tuple[list[ValidationRuleResult], bool]:
    """Run all deterministic rules. Returns (results, has_blocking_failure)."""
    results = [r(fields).to_schema() for r in _RULES]
    has_block = any(r.severity == "block" and not r.passed for r in results)
    return results, has_block
