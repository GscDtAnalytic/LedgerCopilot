"""compare_metrics ↔ run_gate parity + gated-flag correctness.

The UI compare/gate verdict is computed by compare_metrics; the CLI uses run_gate.
These must never disagree on pass/fail — divergence is exactly the bug this change
fixes (the old frontend gated on supplier_name, which is informational). We assert
parity over the real sample scorecards and a grid of synthetic ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval.gate import compare_metrics, run_gate

_SCORECARDS = Path(__file__).resolve().parents[1] / "scorecards"


def _load(name: str) -> dict:
    return json.loads((_SCORECARDS / name).read_text())


def _gate_passed(candidate: dict, baseline: dict) -> bool:
    """Aggregate pass/fail from compare_metrics (only gated metrics block)."""
    return all(m.passed for m in compare_metrics(candidate, baseline) if m.gated)


def test_production_vs_itself_passes() -> None:
    base = _load("production.json")
    assert _gate_passed(base, base) is True
    passed, _ = run_gate(base, base)
    assert passed is True


def test_bad_candidate_is_blocked_with_reasons() -> None:
    candidate = _load("candidate_v2_bad.json")
    baseline = _load("production.json")

    assert _gate_passed(candidate, baseline) is False
    passed, _violations = run_gate(candidate, baseline)
    assert passed is False

    failed = {m.key for m in compare_metrics(candidate, baseline) if m.gated and not m.passed}
    # Bad candidate: false_auto_approve 2.5% > baseline+1pp, and critical_field_acc 0.65 < 0.85.
    assert "false_auto_approve_rate" in failed
    assert "critical_field_accuracy" in failed


def test_supplier_name_is_informational_not_gated() -> None:
    """supplier_name_accuracy must never block, even at 0%."""
    baseline = _load("production.json")
    candidate = {**baseline, "supplier_name_accuracy": 0.0}
    verdicts = {m.key: m for m in compare_metrics(candidate, baseline)}

    assert verdicts["supplier_name_accuracy"].gated is False
    assert verdicts["supplier_name_accuracy"].passed is True
    assert _gate_passed(candidate, baseline) is True  # supplier crash does not block


def test_gated_flags_match_documented_rules() -> None:
    base = _load("production.json")
    gated = {m.key for m in compare_metrics(base, base) if m.gated}
    assert gated == {
        "false_auto_approve_rate",
        "avg_cost_per_doc",
        "critical_field_accuracy",
        "decision_accuracy",
    }


@pytest.mark.parametrize(
    "candidate",
    [
        {"false_auto_approve_rate": 0.0, "critical_field_accuracy": 1.0, "decision_accuracy": 0.85},
        {
            "false_auto_approve_rate": 0.05,
            "critical_field_accuracy": 1.0,
            "decision_accuracy": 0.85,
        },
        {"false_auto_approve_rate": 0.0, "critical_field_accuracy": 0.5, "decision_accuracy": 0.85},
        {"false_auto_approve_rate": 0.0, "critical_field_accuracy": 1.0, "decision_accuracy": 0.10},
        {
            "false_auto_approve_rate": 0.0,
            "critical_field_accuracy": 1.0,
            "decision_accuracy": 0.85,
            "avg_cost_per_doc": 0.05,
        },
    ],
)
def test_parity_run_gate_vs_compare_metrics(candidate: dict) -> None:
    baseline = {
        "false_auto_approve_rate": 0.0,
        "critical_field_accuracy": 1.0,
        "decision_accuracy": 0.85,
        "avg_cost_per_doc": 0.01,
    }
    run_gate_passed, _ = run_gate(candidate, baseline)
    assert _gate_passed(candidate, baseline) == run_gate_passed
