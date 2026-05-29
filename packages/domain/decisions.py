"""Decision orchestration — pure function, no I/O.

Implements the Tree-of-Thoughts decision logic (prompt doc §1.8).
Extracted from workers/pipeline.py so the pipeline worker AND the eval runner
share the exact same decision logic — a scorecard measures what production runs.
"""

from __future__ import annotations

from packages.domain.entities import DecisionBranches, ExtractionOutput
from packages.domain.enums import Decision


def decide(
    fields: ExtractionOutput,
    has_blocking_failure: bool,
    risk_score: float,
    requires_human: bool,
    injection_suspected: bool = False,
) -> tuple[Decision, str, DecisionBranches, str]:
    """Tree-of-Thoughts decision (prompt doc §1.8).

    Evaluates three candidate branches, scores each, picks the survivor.
    Returns (decision, reason_code, branches, justification).

    Invariants:
    - injection_suspected always forces human_review.
    - Auto-approve requires: no blocking failure, no policy escalation,
      confidence >= 0.85, and no injection signal.
    - risk_score >= 1.0 signals a hard deterministic block → reject branch.
    """
    confidence = fields.overall_confidence()

    # Injection suspicion always escalates — never auto-approve untrusted content.
    if injection_suspected:
        requires_human = True

    auto_score = 0.0
    review_score = 0.5  # safe default: escalation is always acceptable
    reject_score = 0.0

    # auto_approve: all critical fields confident, no block, no policy flag.
    if not has_blocking_failure and not requires_human and confidence >= 0.85:
        auto_score = confidence

    # reject: hard deterministic block (risk_score == 1.0 signals confirmed duplicate
    # or other hard-block policy; does not override requires_human).
    if risk_score >= 1.0 and not requires_human:
        reject_score = 0.8

    review_score = max(review_score, 1.0 - auto_score - reject_score)

    branches = DecisionBranches(
        auto_approve=round(auto_score, 3),
        human_review=round(review_score, 3),
        reject=round(reject_score, 3),
    )

    if auto_score > review_score and auto_score > reject_score:
        decision = Decision.AUTO_APPROVE
        reason_code = "clean_match"
        justification = (
            f"All critical fields extracted with confidence {confidence:.0%} "
            "and no blocking validation failures."
        )
    elif reject_score > review_score:
        decision = Decision.REJECT
        reason_code = "hard_block"
        justification = "Hard rejection criteria met (deterministic block from policy engine)."
    else:
        decision = Decision.HUMAN_REVIEW
        reasons: list[str] = []
        if injection_suspected:
            reasons.append("injection_suspected")
        if has_blocking_failure:
            reasons.append("blocking_validation_failure")
        if requires_human:
            reasons.append("policy_requires_review")
        if confidence < 0.85:
            reasons.append(f"low_confidence({confidence:.0%})")
        reason_code = "+".join(reasons) or "insufficient_evidence"
        justification = (
            f"Escalated for human review: {reason_code}. "
            "Confidence or validation results do not meet auto-approve threshold."
        )

    return decision, reason_code, branches, justification
