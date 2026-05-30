"""The case state machine.

received → classified → extracted → validated → reconciled → policy_evaluated → decided
   decided ─┬─ auto_approved → closed
            ├─ rejected → closed
            └─ in_human_review ─┬─ approved → closed
                                ├─ rejected → closed
                                └─ edited → (back to extracted, so validation re-runs)

This module is pure: it only answers "is this transition legal?". Persisting the
transition and writing the accompanying immutable `audit_event` in the same DB
transaction is the caller's job at the I/O boundary. There is no
case mutation without an event.
"""

from __future__ import annotations

from enum import StrEnum


class CaseStatus(StrEnum):
    """Every status a `case` can hold."""

    RECEIVED = "received"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    RECONCILED = "reconciled"
    POLICY_EVALUATED = "policy_evaluated"
    DECIDED = "decided"
    AUTO_APPROVED = "auto_approved"
    IN_HUMAN_REVIEW = "in_human_review"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    CLOSED = "closed"


# The only legal transitions. Anything not listed here is rejected.
ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.RECEIVED: frozenset({CaseStatus.CLASSIFIED}),
    CaseStatus.CLASSIFIED: frozenset({CaseStatus.EXTRACTED}),
    CaseStatus.EXTRACTED: frozenset({CaseStatus.VALIDATED}),
    CaseStatus.VALIDATED: frozenset({CaseStatus.RECONCILED}),
    CaseStatus.RECONCILED: frozenset({CaseStatus.POLICY_EVALUATED}),
    CaseStatus.POLICY_EVALUATED: frozenset({CaseStatus.DECIDED}),
    CaseStatus.DECIDED: frozenset(
        {CaseStatus.AUTO_APPROVED, CaseStatus.REJECTED, CaseStatus.IN_HUMAN_REVIEW}
    ),
    CaseStatus.AUTO_APPROVED: frozenset({CaseStatus.CLOSED}),
    # A reviewer can resend a case to an earlier stage (resend_to_stage action);
    # the resumable pipeline re-runs from there. EXTRACTED/VALIDATED are the only
    # safe re-entry points (deterministic stages, no lost human work).
    CaseStatus.IN_HUMAN_REVIEW: frozenset(
        {
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
            CaseStatus.EDITED,
            CaseStatus.EXTRACTED,
            CaseStatus.VALIDATED,
        }
    ),
    CaseStatus.APPROVED: frozenset({CaseStatus.CLOSED}),
    # An edited case re-enters at EXTRACTED so the deterministic validation stage
    # re-runs on the corrected fields. Re-entering at VALIDATED (the old behaviour)
    # skipped validation and reused the stale ValidationResult, so a human fixing a
    # field could never clear the blocking failure that caused the escalation.
    CaseStatus.EDITED: frozenset({CaseStatus.EXTRACTED}),
    CaseStatus.REJECTED: frozenset({CaseStatus.CLOSED}),
    CaseStatus.CLOSED: frozenset(),
}


class InvalidTransitionError(ValueError):
    """Raised when a transition is not permitted by the state machine."""

    def __init__(self, current: CaseStatus, target: CaseStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"illegal case transition: {current} -> {target}")


def is_terminal(status: CaseStatus) -> bool:
    """True if no further transition is possible from `status`."""
    return not ALLOWED_TRANSITIONS[status]


def is_valid_transition(current: CaseStatus, target: CaseStatus) -> bool:
    """True if moving from `current` to `target` is allowed."""
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: CaseStatus, target: CaseStatus) -> None:
    """Raise `InvalidTransitionError` unless the transition is allowed."""
    if not is_valid_transition(current, target):
        raise InvalidTransitionError(current, target)
