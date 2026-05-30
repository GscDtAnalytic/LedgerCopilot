"""Review Assistant agent (Agent 6) — turns the structured signals of a decided
case into a short, analyst-facing explanation.

Produces the one-line justification the analyst reads in the inbox, e.g.
*"Sent to review for value mismatch and new supplier."* — never the raw LLM
chain-of-thought.

Deterministic-first: the explanation is composed from the structured outputs the
deterministic engines already produced (validation rules, policy decisions,
reconciliation deltas), not from a fresh LLM call. This keeps the explanation
faithful to what drove the decision and costs nothing per case.

Output language is English to match the product UI; BR fiscal domain terms stay
as-is in the data.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from packages.domain.enums import Decision


class ReviewSignals(BaseModel):
    """Structured drivers of the decision, mapped from the pipeline's engines.

    Every field is a fact already computed deterministically upstream — the assistant
    only translates them into analyst language. Booleans default to the safe/no-signal
    value so a partially-populated signal set still produces a sensible explanation.
    """

    decision: str  # Decision value
    confidence: float = 0.0
    has_blocking_failure: bool = False
    failed_block_rules: list[str] = Field(default_factory=list)
    injection_suspected: bool = False
    supplier_unknown: bool = False
    value_mismatch: bool = False
    value_delta_pct: float | None = None
    duplicate_of: str | None = None  # marker/case id of the confirmed duplicate
    supplier_blocklisted: bool = False
    missing_purchase_order: bool = False


class ReviewExplanation(BaseModel):
    """What the analyst sees, plus the auditable structure behind it."""

    summary: str  # one-line, analyst language → stored as case.justification
    reasons: list[str]  # granular tags → joined into case.reason_code
    evidence_refs: list[str]  # prompt doc §1.11 evidence_refs


def _delta_suffix(pct: float | None) -> str:
    if pct is None:
        return ""
    return f" (+{pct:.0%})" if pct >= 0 else f" ({pct:.0%})"


def build_explanation(signals: ReviewSignals) -> ReviewExplanation:
    """Compose the analyst explanation from structured decision signals."""
    decision = signals.decision
    conf_pct = f"{signals.confidence:.0%}"

    # ── Auto-approve ─────────────────────────────────────────────────────────
    if decision == Decision.AUTO_APPROVE:
        return ReviewExplanation(
            summary=(
                f"Auto-approved: all critical fields confident ({conf_pct}) "
                "with no blocking validation, policy or reconciliation issues."
            ),
            reasons=["clean_match"],
            evidence_refs=["validate#all_passed", "reconcile#match"],
        )

    # ── Reject (deterministic hard blocks first) ─────────────────────────────
    if decision == Decision.REJECT:
        if signals.duplicate_of:
            return ReviewExplanation(
                summary=(
                    f"Rejected as a duplicate of {signals.duplicate_of}. "
                    "Paying the same document twice is the worst financial error."
                ),
                reasons=[f"duplicate_of:{signals.duplicate_of}"],
                evidence_refs=[f"duplicate:{signals.duplicate_of}"],
            )
        if signals.supplier_blocklisted:
            return ReviewExplanation(
                summary="Rejected: supplier is on the blocklist.",
                reasons=["supplier_blocklisted"],
                evidence_refs=["supplier_registry#blocklisted"],
            )
        return ReviewExplanation(
            summary="Rejected: deterministic hard-block criteria met.",
            reasons=["hard_block"],
            evidence_refs=["policy#hard_block"],
        )

    # ── Human review — translate each signal into an analyst phrase ──────────
    phrases: list[str] = []
    reasons: list[str] = []
    evidence: list[str] = []

    if signals.injection_suspected:
        phrases.append("suspected prompt injection in the document")
        reasons.append("injection_suspected")
        evidence.append("sanitize#injection_suspected")
    if signals.value_mismatch:
        phrases.append(f"value mismatch{_delta_suffix(signals.value_delta_pct)}")
        reasons.append("value_mismatch")
        evidence.append("reconcile#value_delta")
    if signals.supplier_unknown:
        phrases.append("new supplier")
        reasons.append("supplier_unknown")
        evidence.append("supplier_registry#unknown")
    if signals.missing_purchase_order:
        phrases.append("missing purchase order")
        reasons.append("missing_purchase_order")
        evidence.append("lookup_po#missing")
    if signals.has_blocking_failure:
        rules = ", ".join(signals.failed_block_rules) if signals.failed_block_rules else "rules"
        phrases.append(f"failed validation ({rules})")
        reasons.append("blocking_validation")
        evidence.extend(f"validate#{r}" for r in signals.failed_block_rules)
    # Low confidence is only worth surfacing if nothing more specific explains it.
    if signals.confidence < 0.85 and not phrases:
        phrases.append(f"low extraction confidence ({conf_pct})")
        reasons.append("low_confidence")
        evidence.append("extract#overall_confidence")

    if not phrases:
        phrases.append("insufficient evidence to auto-approve")
        reasons.append("insufficient_evidence")

    summary = f"Sent to review for {_join_phrases(phrases)}."
    return ReviewExplanation(summary=summary, reasons=reasons, evidence_refs=evidence)


def _join_phrases(phrases: list[str]) -> str:
    """Human list join: 'a', 'a and b', 'a, b and c'."""
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"
