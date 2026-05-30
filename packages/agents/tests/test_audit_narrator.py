"""Tests for the Audit Narrator agent (Agent 7) — narrates the event stream."""

from __future__ import annotations

from packages.agents.audit_narrator import AuditEventView, narrate


def _ev(frm: str, to: str, payload: dict | None = None, actor: str = "system") -> AuditEventView:
    return AuditEventView(from_status=frm, to_status=to, actor_type=actor, payload=payload or {})


def test_empty_stream():
    assert "No audit events" in narrate([])


def test_full_human_review_story():
    events = [
        _ev("received", "classified", {"document_type": "invoice", "language": "pt"}),
        _ev(
            "classified",
            "extracted",
            {"overall_confidence": 0.72, "low_agreement_fields": ["total_amount"]},
        ),
        _ev("extracted", "validated", {"rules_run": 8, "passed": 8, "has_blocking_failure": False}),
        _ev("validated", "reconciled", {"matched": False, "deltas": [{"field": "total_amount"}]}),
        _ev(
            "reconciled",
            "policy_evaluated",
            {"risk_score": 0.4, "policies": [{"id": "p-supplier-unknown", "req_human": True}]},
        ),
        _ev("policy_evaluated", "decided", {"reason_code": "value_mismatch+supplier_unknown"}),
        _ev(
            "decided",
            "in_human_review",
            {"justification": "Sent to review for value mismatch and new supplier."},
        ),
    ]
    story = narrate(events)
    assert "classified as invoice" in story
    assert "language pt" in story
    assert "72% overall confidence" in story
    assert "low agreement on total_amount" in story
    assert "p-supplier-unknown" in story
    assert "value_mismatch+supplier_unknown" in story
    assert "Final outcome: in human review" in story
    assert "Sent to review for value mismatch and new supplier." in story


def test_duplicate_reject_story():
    events = [
        _ev("received", "classified", {"document_type": "boleto"}),
        _ev("validated", "reconciled", {"reject_reason": "duplicate_invoice", "matched": False}),
        _ev("decided", "rejected", {"justification": "Rejected as a duplicate of CASE-1."}),
    ]
    story = narrate(events)
    assert "hard block: duplicate_invoice" in story
    assert "Final outcome: rejected" in story


def test_dead_letter_event_is_narrated():
    events = [
        _ev(
            "extracted",
            "extracted",
            {"event": "pipeline_dead_letter", "error_type": "TimeoutError"},
        )
    ]
    assert "dead-lettered (TimeoutError)" in narrate(events)


def test_human_action_narrated():
    events = [_ev("in_human_review", "approved", {}, actor="human")]
    # actor_id is None here → falls back to "reviewer"
    assert "approved the case" in narrate(events)
