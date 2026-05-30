"""Deterministic validation engine — pure functions, no LLM, no I/O.

Each rule receives data and returns a result + reason. A severity="block" result
prevents auto_approve regardless of extraction confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from packages.domain.entities import ExtractionOutput, ValidationRuleResult

# Tolerance for the "sum of line items must equal total" check.
_ITEMS_SUM_TOLERANCE = 0.01  # 1%


class ValidationContext(BaseModel):
    """External reference data injected by the pipeline at the I/O boundary.

    The engine stays pure (data in, result out) while supporting membership-style
    rules like cost-center validity. When a field is None, that rule degrades to
    a non-blocking warn.
    """

    valid_cost_centers: frozenset[str] | None = None


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


# ─── Individual rules ────────────────────────────────────────────────────────


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


def _validate_cnpj_check_digits(digits: str) -> bool:
    """Validate CNPJ check digits using the official Brazilian Mod-11 algorithm."""
    if len(set(digits)) == 1:
        return False  # 00000000000000 and similar are invalid by definition

    def _calc(nums: list[int], weights: list[int]) -> int:
        total = sum(n * w for n, w in zip(nums, weights, strict=True))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    nums = [int(d) for d in digits]
    first_weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    second_weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    return (
        _calc(nums[:12], first_weights) == nums[12] and _calc(nums[:13], second_weights) == nums[13]
    )


def _rule_cnpj_valid(fields: ExtractionOutput) -> RuleResult:
    """Validate CNPJ check digits (Brazilian Mod-11). Requires cnpj_format to pass."""
    fv = fields.tax_id_cnpj
    if fv is None or not fv.value:
        return RuleResult("cnpj_valid", False, "warn", "no CNPJ to validate")
    digits = re.sub(r"\D", "", str(fv.value))
    if len(digits) != 14:
        return RuleResult("cnpj_valid", False, "warn", "cnpj_format failed — skipping check digits")
    if not _validate_cnpj_check_digits(digits):
        return RuleResult("cnpj_valid", False, "block", f"CNPJ check digits invalid: {fv.value}")
    return RuleResult("cnpj_valid", True, "block")


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


def _rule_date_order(fields: ExtractionOutput) -> RuleResult:
    """issue_date must be <= due_date when both are present and parseable."""
    issue_fv = fields.issue_date
    due_fv = fields.due_date
    if issue_fv is None or issue_fv.value is None or due_fv is None or due_fv.value is None:
        return RuleResult("date_order", True, "warn")  # can't check without both dates
    try:
        issue = date.fromisoformat(str(issue_fv.value))
        due = date.fromisoformat(str(due_fv.value))
        if due < issue:
            return RuleResult(
                "date_order",
                False,
                "block",
                f"due_date {due} is before issue_date {issue}",
            )
    except ValueError:
        return RuleResult("date_order", False, "warn", "could not parse dates for comparison")
    return RuleResult("date_order", True, "warn")


def _rule_items_sum_matches_total(fields: ExtractionOutput) -> RuleResult:
    """Sum of line-item totals must equal total_amount.

    Skipped (pass/warn) when there are no items or no total to compare against —
    a document without an itemised breakdown is not a failure. When items ARE
    present and their sum deviates from the total beyond tolerance, it blocks.
    """
    if not fields.items:
        return RuleResult("items_sum_matches_total", True, "warn", "no line items to sum")
    total_fv = fields.total_amount
    if total_fv is None or total_fv.value is None:
        return RuleResult("items_sum_matches_total", True, "warn", "no total to compare against")
    line_totals = [i.line_total for i in fields.items if i.line_total is not None]
    if not line_totals:
        return RuleResult("items_sum_matches_total", True, "warn", "line items lack line_total")
    try:
        total = float(total_fv.value)
    except (TypeError, ValueError):
        return RuleResult("items_sum_matches_total", True, "warn", "total is not numeric")
    items_sum = sum(line_totals)
    if total == 0:
        return RuleResult("items_sum_matches_total", items_sum == 0, "block", f"sum={items_sum}")
    delta = abs(items_sum - total) / abs(total)
    if delta > _ITEMS_SUM_TOLERANCE:
        return RuleResult(
            "items_sum_matches_total",
            False,
            "block",
            f"items sum {items_sum:.2f} != total {total:.2f} (delta {delta:.1%})",
        )
    return RuleResult("items_sum_matches_total", True, "block")


def _rule_cost_center_valid(
    fields: ExtractionOutput, context: ValidationContext | None
) -> RuleResult:
    """Cost center, when present, must be one of the org's active codes.

    Without a context (valid_cost_centers=None) the engine cannot verify membership,
    so presence is a non-blocking warn. With a context, an unknown code blocks.
    """
    fv = fields.cost_center
    if fv is None or not fv.value:
        return RuleResult("cost_center_present", False, "warn", "cost_center not extracted")
    if context is None or context.valid_cost_centers is None:
        return RuleResult("cost_center_valid", True, "warn", "no registry to validate against")
    code = str(fv.value).strip()
    if code not in context.valid_cost_centers:
        return RuleResult(
            "cost_center_valid", False, "block", f"cost_center '{code}' not in active registry"
        )
    return RuleResult("cost_center_valid", True, "block")


# Rules that depend only on the extracted fields.
_RULES = [
    _rule_amount_non_negative,
    _rule_cnpj_present,
    _rule_cnpj_format,
    _rule_cnpj_valid,
    _rule_currency_present,
    _rule_document_number_present,
    _rule_supplier_name_present,
    _rule_date_order,
    _rule_items_sum_matches_total,
]


def run_validations(
    fields: ExtractionOutput, context: ValidationContext | None = None
) -> tuple[list[ValidationRuleResult], bool]:
    """Run all deterministic rules. Returns (results, has_blocking_failure).

    `context` carries injected reference data (e.g. valid cost-center codes). It is
    optional so existing callers/tests that only pass `fields` keep working.
    """
    results = [r(fields).to_schema() for r in _RULES]
    # Context-dependent rules run separately (they need the injected reference data).
    results.append(_rule_cost_center_valid(fields, context).to_schema())
    has_block = any(r.severity == "block" and not r.passed for r in results)
    return results, has_block
