"""Versioned policy engine — deterministic, pure, no LLM.

Each policy is a named rule that takes extraction fields + validation results and
returns a PolicyDecision. Rules are pure functions; I/O (supplier lookup, PO
retrieval) is resolved by the pipeline before calling this module.

Current alias: 'dev' — the Phase 2 essential ruleset.
Phase 3 adds DB-backed versioning, gating, and the full set from 
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.domain.entities import ExtractionOutput


@dataclass(frozen=True)
class PolicyDecision:
    policy_id: str
    verdict: str  # pass | block | escalate
    requires_human: bool
    reason: str
    risk_delta: float = 0.0  # additive contribution to overall risk_score


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


def run_policy(
    *,
    fields: ExtractionOutput,
    has_blocking_failure: bool,
    supplier_registered: bool = False,
    po_total: float | None = None,
) -> tuple[list[PolicyDecision], float, bool]:
    """Run all active policies for the 'dev' alias.

    Returns (decisions, risk_score, requires_human).
    risk_score is clamped to [0, 1].
    """
    decisions = [
        _policy_low_confidence(fields, has_blocking_failure),
        _policy_supplier_unknown(supplier_registered),
    ]

    # Amount delta only when we have a PO total and extraction succeeded.
    extracted_total_fv = fields.total_amount
    if extracted_total_fv is not None and isinstance(extracted_total_fv.value, float | int):
        decisions.append(_policy_amount_delta(float(extracted_total_fv.value), po_total))

    risk_score = min(1.0, sum(d.risk_delta for d in decisions))
    requires_human = any(d.requires_human for d in decisions)
    return decisions, risk_score, requires_human
