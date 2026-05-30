"""Audit Narrator agent (Agent 7) — summarises *why* the final decision happened,
reading the immutable audit-event stream of a case.

The case state and its explanation are fully derivable from the append-only
``audit_events`` log. The narrator never re-computes anything — it walks the
events the pipeline already wrote and turns each transition's payload into a sentence,
so the story it tells is exactly what happened, in order.

Deterministic by default: a template walk over known payload keys, no LLM. An LLM can
later rewrite the joined narrative for tone, but the per-event facts are auditable.

Decoupled from the ORM: callers map their ``AuditEvent`` rows into ``AuditEventView``
so this module stays pure and unit-testable without a database.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditEventView(BaseModel):
    """A read-only projection of one audit_events row."""

    from_status: str
    to_status: str
    actor_type: str  # system | human | agent
    actor_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _narrate_event(ev: AuditEventView) -> str | None:
    """One sentence for one transition. Returns None for transitions not worth narrating."""
    p = ev.payload
    frm, to = ev.from_status, ev.to_status

    # Dead letter first: it reuses from==to on a known stage, so it must win over
    # the stage branches below.
    if p.get("event") == "pipeline_dead_letter":
        return f"Pipeline failed and was dead-lettered ({p.get('error_type', 'error')})."

    # System/agent pipeline stages ------------------------------------------------
    if to == "classified":
        doc_type = p.get("document_type", "document")
        lang = p.get("language")
        bits = f"Received and classified as {doc_type}"
        if p.get("out_of_scope_reason"):
            bits += f" (out of scope: {p['out_of_scope_reason']})"
        if lang and lang != "unknown":
            bits += f", language {lang}"
        return bits + "."

    if to == "extracted":
        conf = p.get("overall_confidence")
        sent = "Fields extracted"
        if isinstance(conf, int | float):
            sent += f" with {conf:.0%} overall confidence"
        low = p.get("low_agreement_fields") or []
        if low:
            sent += f"; low agreement on {', '.join(low)}"
        if p.get("injection_suspected"):
            sent += "; suspected prompt injection flagged"
        return sent + "."

    if to == "validated":
        if frm == "edited":
            return "Edited values re-entered the pipeline at validation."
        passed = p.get("passed")
        total = p.get("rules_run")
        sent = "Deterministic validation ran"
        if passed is not None and total is not None:
            sent += f" ({passed}/{total} rules passed)"
        if p.get("has_blocking_failure"):
            sent += " with a blocking failure"
        return sent + "."

    if to == "reconciled":
        if p.get("reject_reason"):
            return f"Reconciliation hit a hard block: {p['reject_reason']}."
        if p.get("matched"):
            return "Reconciliation matched the expected context."
        deltas = p.get("deltas") or []
        if deltas:
            return f"Reconciliation found {len(deltas)} discrepancy(ies) versus expected context."
        return "Reconciliation completed."

    if to == "policy_evaluated":
        risk = p.get("risk_score")
        sent = "Policy evaluated"
        if isinstance(risk, int | float):
            sent += f" (risk {risk:.2f})"
        escalating = [
            pol.get("id", "?") for pol in (p.get("policies") or []) if pol.get("req_human")
        ]
        if escalating:
            sent += f"; escalating policies: {', '.join(escalating)}"
        return sent + "."

    if to == "decided":
        reason = p.get("reason_code")
        return f"Decision reached (reason: {reason})." if reason else "Decision reached."

    if to in {"auto_approved", "rejected", "in_human_review"}:
        label = to.replace("_", " ")
        just = p.get("justification")
        return f"Final outcome: {label}. {just}" if just else f"Final outcome: {label}."

    # Human review actions --------------------------------------------------------
    if frm == "in_human_review" and to in {"approved", "rejected", "edited"}:
        who = ev.actor_id or "reviewer"
        return f"Human {who} {to} the case."

    return None


def narrate(events: list[AuditEventView]) -> str:
    """Produce a short narrative of the case from its ordered audit events.

    Events must be passed in chronological order (the caller orders by occurred_at).
    """
    if not events:
        return "No audit events recorded for this case yet."

    sentences = [s for ev in events if (s := _narrate_event(ev)) is not None]
    if not sentences:
        return "No narratable events recorded for this case yet."
    return " ".join(sentences)
