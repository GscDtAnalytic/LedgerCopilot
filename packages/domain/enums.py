"""Core domain enumerations shared across the platform."""

from __future__ import annotations

from enum import StrEnum


class ActorType(StrEnum):
    """Who caused a state transition. Recorded on every `audit_event`."""

    SYSTEM = "system"
    HUMAN = "human"
    AGENT = "agent"


class Decision(StrEnum):
    """The three traceable decisions the orchestration agent may reach.

    `human_review` is the safe default: escalating is never a failure, while a
    wrongful `auto_approve` is the worst error in the system.
    """

    AUTO_APPROVE = "auto_approve"
    HUMAN_REVIEW = "human_review"
    REJECT = "reject"


class DocumentType(StrEnum):
    """Supported financial document types; anything else is out of scope."""

    INVOICE = "invoice"
    BOLETO = "boleto"
    RECEIPT = "receipt"
    OUT_OF_SCOPE = "out_of_scope"
