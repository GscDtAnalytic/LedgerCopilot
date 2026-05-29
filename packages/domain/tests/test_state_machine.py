"""Tests for the case state machine. Pure, no fixtures needed."""

from __future__ import annotations

from itertools import pairwise

import pytest

from packages.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    CaseStatus,
    InvalidTransitionError,
    assert_transition,
    is_terminal,
    is_valid_transition,
)


def test_every_status_has_a_transition_entry() -> None:
    # The map must be exhaustive so `is_terminal`/`is_valid_transition` never KeyError.
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)


def test_happy_path_pipeline_is_legal() -> None:
    path = [
        CaseStatus.RECEIVED,
        CaseStatus.CLASSIFIED,
        CaseStatus.EXTRACTED,
        CaseStatus.VALIDATED,
        CaseStatus.RECONCILED,
        CaseStatus.POLICY_EVALUATED,
        CaseStatus.DECIDED,
        CaseStatus.AUTO_APPROVED,
        CaseStatus.CLOSED,
    ]
    for current, target in pairwise(path):
        assert is_valid_transition(current, target)


def test_edited_returns_to_validated() -> None:
    assert is_valid_transition(CaseStatus.EDITED, CaseStatus.VALIDATED)


def test_closed_is_terminal() -> None:
    assert is_terminal(CaseStatus.CLOSED)
    assert not is_terminal(CaseStatus.RECEIVED)


def test_cannot_skip_steps() -> None:
    assert not is_valid_transition(CaseStatus.RECEIVED, CaseStatus.DECIDED)


def test_assert_transition_raises_on_illegal_move() -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(CaseStatus.CLOSED, CaseStatus.RECEIVED)
