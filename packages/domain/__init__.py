"""Domain entities, enums and the case state machine (pure, no I/O).

This package is the single source of truth for the vocabulary used everywhere
else: actor types, decisions, document types and the legal transitions a case
may take. Every state transition in the system must be expressed through the
state machine here and accompanied by an `audit_event` at the I/O boundary
.
"""

from packages.domain.enums import ActorType, Decision, DocumentType
from packages.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    CaseStatus,
    InvalidTransitionError,
    is_terminal,
    is_valid_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ActorType",
    "CaseStatus",
    "Decision",
    "DocumentType",
    "InvalidTransitionError",
    "is_terminal",
    "is_valid_transition",
]
