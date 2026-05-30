"""The seven agents, each with a rigid contract (no open-ended autonomy).

LLM-backed vs. deterministic:
  1. Intake          — deterministic (``intake.py``): type, language, parse, quality.
  2. Extraction      — LLM (``extraction.py``): Self-Consistency k=3, Pydantic-validated.
  3. Validation      — deterministic (``packages.validation``): suggests, never decides.
  4. Policy          — deterministic (``packages.policy``): company rules + risk.
  5. Reconciliation  — deterministic (``packages.reconciliation``): entity comparison.
  6. Review Assistant— deterministic (``review_assistant.py``): analyst-facing explanation.
  7. Audit Narrator  — deterministic (``audit_narrator.py``): narrates the event stream.

Only Extraction calls a model. Every model call goes through ``packages.ai_gateway``
and captures a trace referencing a ``prompt_version_id``.
"""
