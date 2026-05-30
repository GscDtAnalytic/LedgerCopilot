"""Deterministic validation engine (pure, no I/O).

The rules here are pure functions that take data and return a result plus a reason —
never a prompt. Rules cover: non-negative amount, valid CNPJ, due date >= issue date,
currency present, line items sum to total, valid cost center. A failure of severity
``block`` prevents ``auto_approve`` regardless of confidence.
"""
