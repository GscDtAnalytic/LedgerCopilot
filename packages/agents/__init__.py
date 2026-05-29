"""The seven agents, each with a rigid contract (no open-ended autonomy).

Intake, Extraction (output validated by Pydantic), Validation (suggests, does not
decide), Policy, Reconciliation, Review Assistant (short analyst-facing
explanation) and Audit Narrator. See  and the prompt doc for each
contract. Every model call goes through ``packages.ai_gateway`` and captures a
trace referencing a ``prompt_version_id``.
"""
