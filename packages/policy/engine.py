"""Versioned policy engine — deterministic, pure, no LLM.

Each policy is a named rule that takes extraction fields + validation results and
returns a PolicyDecision. Rules are pure functions; I/O (supplier lookup, PO
retrieval) is resolved by the pipeline before calling this module.

Current alias: 'dev' — the Phase 2 essential ruleset.
Phase 3 adds DB-backed versioning, gating, and the full set from 
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from packages.domain.entities import ExtractionOutput

# Amount above which a document can never auto-approve.
_AUTO_APPROVE_AMOUNT_LIMIT = 5000.0
# Spend categories that require an explicit justification before auto-approval.
_CATEGORIES_REQUIRING_JUSTIFICATION = frozenset({"legal", "consulting", "travel", "marketing"})
# A payment due within this many days of issue is "urgent" → double check.
_URGENT_DUE_DAYS = 3


@dataclass(frozen=True)
class PolicyDecision:
    policy_id: str
    verdict: str  # pass | block | escalate
    requires_human: bool
    reason: str
    risk_delta: float = 0.0  # additive contribution to overall risk_score
    # Urgent payments need a second approver. The signal is surfaced
    # in the HITL UI; enforcing a true two-approver state machine is future work.
    requires_dual_approval: bool = False


def _policy_low_confidence(
    fields: ExtractionOutput,
    has_blocking_failure: bool,
) -> PolicyDecision:
    """Escalate when extraction confidence is below the auto-approve threshold."""
    confidence = fields.overall_confidence()
    if has_blocking_failure:
        return PolicyDecision(
            policy_id="p-blocking-validation",
            verdict="block",
            requires_human=True,
            reason=f"blocking_validation_failure (confidence={confidence:.2f})",
            risk_delta=0.6,
        )
    if confidence < 0.50:
        return PolicyDecision(
            policy_id="p-low-confidence",
            verdict="escalate",
            requires_human=True,
            reason=f"overall_confidence={confidence:.2f} < 0.50",
            risk_delta=0.5,
        )
    if confidence < 0.85:
        return PolicyDecision(
            policy_id="p-medium-confidence",
            verdict="escalate",
            requires_human=True,
            reason=f"overall_confidence={confidence:.2f} < 0.85",
            risk_delta=0.3,
        )
    return PolicyDecision(
        policy_id="p-confidence-ok",
        verdict="pass",
        requires_human=False,
        reason=f"confidence={confidence:.2f} >= 0.85",
        risk_delta=0.0,
    )


def _policy_supplier_unknown(
    supplier_registered: bool,
) -> PolicyDecision:
    """New or unregistered supplier: never auto-approve."""
    if not supplier_registered:
        return PolicyDecision(
            policy_id="p-supplier-unknown",
            verdict="escalate",
            requires_human=True,
            reason="supplier not in registry",
            risk_delta=0.3,
        )
    return PolicyDecision(
        policy_id="p-supplier-known",
        verdict="pass",
        requires_human=False,
        reason="supplier registered",
        risk_delta=0.0,
    )


def _policy_amount_delta(
    extracted_total: float | None,
    po_total: float | None,
    delta_threshold: float = 0.10,
) -> PolicyDecision:
    """Escalate when extracted total deviates > threshold from the PO total."""
    if extracted_total is None or po_total is None or po_total == 0:
        return PolicyDecision(
            policy_id="p-amount-delta-missing",
            verdict="escalate",
            requires_human=True,
            reason="cannot verify amount: PO or total missing",
            risk_delta=0.2,
        )
    delta = abs(extracted_total - po_total) / po_total
    if delta > delta_threshold:
        return PolicyDecision(
            policy_id="p-amount-delta",
            verdict="escalate",
            requires_human=True,
            reason=f"value_delta={delta:.1%} > {delta_threshold:.0%} threshold",
            risk_delta=0.4,
        )
    return PolicyDecision(
        policy_id="p-amount-ok",
        verdict="pass",
        requires_human=False,
        reason=f"value_delta={delta:.1%} within threshold",
        risk_delta=0.0,
    )


def _policy_amount_threshold(
    extracted_total: float | None,
    limit: float = _AUTO_APPROVE_AMOUNT_LIMIT,
) -> PolicyDecision:
    """Above the auto-approve limit a human must sign off.

    The single most common finance control: large amounts never auto-approve.
    """
    if extracted_total is None:
        return PolicyDecision(
            policy_id="p-amount-threshold-unknown",
            verdict="escalate",
            requires_human=True,
            reason="total_amount missing — cannot clear amount threshold",
            risk_delta=0.2,
        )
    if extracted_total > limit:
        return PolicyDecision(
            policy_id="p-amount-threshold",
            verdict="escalate",
            requires_human=True,
            reason=f"total {extracted_total:.2f} > auto-approve limit {limit:.2f}",
            risk_delta=0.3,
        )
    return PolicyDecision(
        policy_id="p-amount-under-limit",
        verdict="pass",
        requires_human=False,
        reason=f"total {extracted_total:.2f} <= limit {limit:.2f}",
        risk_delta=0.0,
    )


def _policy_category_justification(
    category: str | None,
    justification_present: bool,
) -> PolicyDecision:
    """Categories like legal/consulting require a justification before auto-approval."""
    if category is None:
        return PolicyDecision(
            policy_id="p-category-na",
            verdict="pass",
            requires_human=False,
            reason="no category extracted — rule not applicable",
        )
    normalised = category.strip().lower()
    if normalised in _CATEGORIES_REQUIRING_JUSTIFICATION and not justification_present:
        return PolicyDecision(
            policy_id="p-category-justification",
            verdict="escalate",
            requires_human=True,
            reason=f"category '{normalised}' requires a justification (none provided)",
            risk_delta=0.2,
        )
    return PolicyDecision(
        policy_id="p-category-ok",
        verdict="pass",
        requires_human=False,
        reason=f"category '{normalised}' does not require extra justification",
    )


def _policy_urgent_payment(
    issue_date: str | None,
    due_date: str | None,
) -> PolicyDecision:
    """Payments due within _URGENT_DUE_DAYS of issue need a double check.

    Deterministic: based purely on the document's own dates, not on today's date,
    so eval runs are reproducible.
    """
    if not issue_date or not due_date:
        return PolicyDecision(
            policy_id="p-urgency-na",
            verdict="pass",
            requires_human=False,
            reason="missing dates — urgency not assessable",
        )
    try:
        issue = date.fromisoformat(str(issue_date))
        due = date.fromisoformat(str(due_date))
    except ValueError:
        return PolicyDecision(
            policy_id="p-urgency-na",
            verdict="pass",
            requires_human=False,
            reason="unparseable dates — urgency not assessable",
        )
    days = (due - issue).days
    if 0 <= days <= _URGENT_DUE_DAYS:
        return PolicyDecision(
            policy_id="p-urgent-payment",
            verdict="escalate",
            requires_human=True,
            reason=f"due in {days}d (<= {_URGENT_DUE_DAYS}d) — urgent payment, double check",
            risk_delta=0.2,
            requires_dual_approval=True,
        )
    return PolicyDecision(
        policy_id="p-not-urgent",
        verdict="pass",
        requires_human=False,
        reason=f"due in {days}d — not urgent",
    )


def run_policy(
    *,
    fields: ExtractionOutput,
    has_blocking_failure: bool,
    supplier_registered: bool = False,
    po_total: float | None = None,
    amount_limit: float = _AUTO_APPROVE_AMOUNT_LIMIT,
    justification_present: bool = False,
) -> tuple[list[PolicyDecision], float, bool]:
    """Run all active policies for the 'dev' alias.

    Returns (decisions, risk_score, requires_human).
    risk_score is clamped to [0, 1].
    """
    extracted_total: float | None = None
    extracted_total_fv = fields.total_amount
    if extracted_total_fv is not None and isinstance(extracted_total_fv.value, float | int):
        extracted_total = float(extracted_total_fv.value)

    category_val = (
        str(fields.category.value)
        if fields.category is not None and fields.category.value is not None
        else None
    )
    issue_val = (
        str(fields.issue_date.value)
        if fields.issue_date is not None and fields.issue_date.value is not None
        else None
    )
    due_val = (
        str(fields.due_date.value)
        if fields.due_date is not None and fields.due_date.value is not None
        else None
    )

    decisions = [
        _policy_low_confidence(fields, has_blocking_failure),
        _policy_supplier_unknown(supplier_registered),
        _policy_amount_threshold(extracted_total, amount_limit),
        _policy_category_justification(category_val, justification_present),
        _policy_urgent_payment(issue_val, due_val),
    ]

    # Amount delta only when we have a PO total and extraction succeeded.
    if extracted_total is not None:
        decisions.append(_policy_amount_delta(extracted_total, po_total))

    risk_score = min(1.0, sum(d.risk_delta for d in decisions))
    requires_human = any(d.requires_human for d in decisions)
    return decisions, risk_score, requires_human
