"""Tests for the Review Assistant agent (Agent 6) — analyst-facing explanation."""

from __future__ import annotations

from packages.agents.review_assistant import ReviewSignals, build_explanation
from packages.domain.enums import Decision


def test_value_mismatch_and_supplier_unknown_reads_like_the_spec():
    """The canonical example: 'sent to review for value mismatch and new supplier'."""
    exp = build_explanation(
        ReviewSignals(
            decision=Decision.HUMAN_REVIEW,
            confidence=0.9,
            value_mismatch=True,
            value_delta_pct=0.10,
            supplier_unknown=True,
        )
    )
    assert exp.summary == "Sent to review for value mismatch (+10%) and new supplier."
    assert exp.reasons == ["value_mismatch", "supplier_unknown"]
    assert "reconcile#value_delta" in exp.evidence_refs
    assert "supplier_registry#unknown" in exp.evidence_refs


def test_auto_approve_explanation():
    exp = build_explanation(ReviewSignals(decision=Decision.AUTO_APPROVE, confidence=0.97))
    assert "Auto-approved" in exp.summary
    assert exp.reasons == ["clean_match"]


def test_reject_duplicate_names_the_case():
    exp = build_explanation(ReviewSignals(decision=Decision.REJECT, duplicate_of="CASE-8821"))
    assert "duplicate of CASE-8821" in exp.summary
    assert exp.reasons == ["duplicate_of:CASE-8821"]


def test_reject_blocklisted():
    exp = build_explanation(ReviewSignals(decision=Decision.REJECT, supplier_blocklisted=True))
    assert exp.reasons == ["supplier_blocklisted"]


def test_blocking_validation_lists_failed_rules():
    exp = build_explanation(
        ReviewSignals(
            decision=Decision.HUMAN_REVIEW,
            confidence=0.4,
            has_blocking_failure=True,
            failed_block_rules=["cnpj_valid", "amount_non_negative"],
        )
    )
    assert "failed validation (cnpj_valid, amount_non_negative)" in exp.summary
    assert "blocking_validation" in exp.reasons
    assert "validate#cnpj_valid" in exp.evidence_refs


def test_low_confidence_only_when_nothing_more_specific():
    exp = build_explanation(ReviewSignals(decision=Decision.HUMAN_REVIEW, confidence=0.6))
    assert "low extraction confidence (60%)" in exp.summary
    assert exp.reasons == ["low_confidence"]


def test_injection_takes_priority_phrase():
    exp = build_explanation(
        ReviewSignals(
            decision=Decision.HUMAN_REVIEW,
            confidence=0.95,
            injection_suspected=True,
        )
    )
    assert "suspected prompt injection" in exp.summary
    assert exp.reasons == ["injection_suspected"]
