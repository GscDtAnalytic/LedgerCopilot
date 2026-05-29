"""Deterministic validation engine (pure, no I/O).

Determinism before LLM: the rules here are pure functions that
take data and return a result plus a reason — never a prompt. Reference rules
(see prompt doc §1.6): non-negative amount, no duplicate by hash/number, valid
CNPJ, due date >= issue date, currency present, line items sum to total,
supplier registered, valid cost center. A failure of severity ``block`` forbids
``auto_approve``.

Phase 1 ships the basic validations; the full engine lands in Phase 2.
"""
