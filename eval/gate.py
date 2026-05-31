"""Decide whether a candidate prompt/policy version may be promoted.

Usage:
    uv run python -m eval.gate --candidate eval/scorecards/dev.json \\
                               --baseline  eval/scorecards/production.json

Or compare by running eval.run first and piping:
    uv run python -m eval.run --out /tmp/candidate.json
    uv run python -m eval.gate --candidate /tmp/candidate.json --baseline /tmp/baseline.json

Exit codes:
    0  — all rules pass; promotion is safe
    1  — one or more rules violated; promotion is BLOCKED

Promotion rules — any violation → exit 1:
    - false_auto_approve_rate  > baseline + 1%
    - cost/doc                 > baseline + 20%
    - critical_field_accuracy  < 85%  (total_amount, tax_id_cnpj, document_number)
    - decision_accuracy        worsens vs baseline by > 5pp

    supplier_name_accuracy is retained in the scorecard as an informational metric
    but is NOT a gate rule: supplier_name is not in critical_fields(), is not SC'd,
    and is not weighted in overall_confidence. Gating on it would measure something
    the pipeline does not control.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Thresholds as named constants — same values used in the promote API endpoint.
MAX_FALSE_AUTO_APPROVE_DELTA = 0.01  # +1pp
MAX_COST_PER_DOC_DELTA_RATIO = 0.20  # +20%
MIN_CRITICAL_FIELD_ACCURACY = 0.85  # total_amount + tax_id_cnpj + document_number
MAX_DECISION_ACCURACY_DROP = 0.05  # -5pp

# Negligible movement below which a metric is "unchanged" (avoids warning-noise on
# floating-point rounding). Rates/accuracies are fractions; cost is in USD.
_EPSILON = 1e-6


@dataclass
class MetricVerdict:
    """One metric compared candidate-vs-baseline, for the UI compare table.

    `gated` distinguishes the four promotion gate rules from informational metrics
    (supplier_name_accuracy, p95_latency_ms, exact_field_accuracy) which are shown
    but never block — see for why supplier_name is informational.
    `severity` is "good" | "warning" | "fail": a gated metric that breaches its
    threshold is "fail"; any metric that regressed without breaching is "warning".
    """

    key: str
    label: str
    candidate: float
    baseline: float | None
    delta: float | None
    threshold_label: str
    gated: bool
    passed: bool
    severity: str  # "good" | "warning" | "fail"


# Per-metric direction: True when a HIGHER value is better (accuracies); False when
# a LOWER value is better (false-approve rate, cost, latency).
_HIGHER_IS_BETTER = {
    "false_auto_approve_rate": False,
    "avg_cost_per_doc": False,
    "p95_latency_ms": False,
    "critical_field_accuracy": True,
    "decision_accuracy": True,
    "supplier_name_accuracy": True,
    "exact_field_accuracy": True,
}


def _regressed(key: str, delta: float | None) -> bool:
    """True when the candidate moved in the worse direction beyond epsilon."""
    if delta is None or abs(delta) <= _EPSILON:
        return False
    return delta < 0 if _HIGHER_IS_BETTER.get(key, True) else delta > 0


def compare_metrics(candidate: dict, baseline: dict) -> list[MetricVerdict]:
    """Compare a candidate scorecard against a baseline, metric by metric.

    Single source of truth for the compare/gate UI and the promote endpoint —
    `run_gate` (CLI) is asserted to agree with this in tests. Gate verdicts use the
    same thresholds as `run_gate`; informational metrics are reported but never fail.
    """
    verdicts: list[MetricVerdict] = []

    def _add(
        key: str,
        label: str,
        threshold_label: str,
        *,
        gated: bool,
        passed: bool,
        baseline_default: float = 0.0,
    ) -> None:
        cand = float(candidate.get(key, 0.0))
        base = baseline.get(key)
        base_f = float(base) if base is not None else baseline_default
        delta = cand - base_f
        if not passed:
            severity = "fail"
        elif _regressed(key, delta):
            severity = "warning"
        else:
            severity = "good"
        verdicts.append(
            MetricVerdict(
                key=key,
                label=label,
                candidate=cand,
                baseline=base_f,
                delta=delta,
                threshold_label=threshold_label,
                gated=gated,
                passed=passed,
                severity=severity,
            )
        )

    # ── Gate rules (block promotion) ───────────────────────────────────────────
    cand_far = float(candidate.get("false_auto_approve_rate", 0.0))
    base_far = float(baseline.get("false_auto_approve_rate", 0.0))
    _add(
        "false_auto_approve_rate",
        "False auto-approve rate",
        "<= baseline + 1pp",
        gated=True,
        passed=cand_far <= base_far + MAX_FALSE_AUTO_APPROVE_DELTA,
    )

    cand_cost = float(candidate.get("avg_cost_per_doc", 0.0))
    base_cost = float(baseline.get("avg_cost_per_doc", 0.0))
    cost_ok = not (base_cost > 0 and cand_cost > base_cost * (1 + MAX_COST_PER_DOC_DELTA_RATIO))
    _add(
        "avg_cost_per_doc",
        "Avg cost / doc",
        "<= baseline x 1.20",
        gated=True,
        passed=cost_ok,
    )

    cand_cfa = float(candidate.get("critical_field_accuracy", 0.0))
    _add(
        "critical_field_accuracy",
        "Critical field accuracy",
        "≥ 85%",
        gated=True,
        passed=cand_cfa >= MIN_CRITICAL_FIELD_ACCURACY,
    )

    cand_da = float(candidate.get("decision_accuracy", 0.0))
    base_da = float(baseline.get("decision_accuracy", 0.0))
    _add(
        "decision_accuracy",
        "Decision accuracy",
        ">= baseline - 5pp",
        gated=True,
        passed=cand_da >= base_da - MAX_DECISION_ACCURACY_DROP,
    )

    # ── Informational (shown, never block) ─────────────────────────────────────
    _add(
        "supplier_name_accuracy",
        "Supplier name accuracy",
        "informational",
        gated=False,
        passed=True,
    )
    _add(
        "exact_field_accuracy",
        "Exact field accuracy",
        "informational",
        gated=False,
        passed=True,
    )
    _add(
        "p95_latency_ms",
        "p95 latency",
        "informational",
        gated=False,
        passed=True,
    )
    return verdicts


def metric_verdicts_to_dicts(verdicts: list[MetricVerdict]) -> list[dict]:
    """Serialise MetricVerdict list (for the API layer)."""
    return [asdict(v) for v in verdicts]


def _load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: scorecard not found: {p}", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text())


def run_gate(candidate: dict, baseline: dict) -> tuple[bool, list[str]]:
    """Check all promotion rules. Returns (passed, violation_messages)."""
    violations: list[str] = []

    # 1. false_auto_approve_rate
    cand_far = candidate.get("false_auto_approve_rate", 0.0)
    base_far = baseline.get("false_auto_approve_rate", 0.0)
    if cand_far > base_far + MAX_FALSE_AUTO_APPROVE_DELTA:
        threshold = f"{base_far:.3f}+{MAX_FALSE_AUTO_APPROVE_DELTA:.2f}"
        violations.append(f"  ✗ false_auto_approve_rate: {cand_far:.3f} > {threshold}")

    # 2. cost/doc
    cand_cost = candidate.get("avg_cost_per_doc", 0.0)
    base_cost = baseline.get("avg_cost_per_doc", 0.0)
    cost_threshold = base_cost * (1 + MAX_COST_PER_DOC_DELTA_RATIO)
    if base_cost > 0 and cand_cost > cost_threshold:
        violations.append(
            f"  ✗ avg_cost_per_doc: {cand_cost:.6f} > {cost_threshold:.6f} (baseline x1.20)"
        )

    # 3. critical_field_accuracy
    cand_cfa = candidate.get("critical_field_accuracy", 0.0)
    if cand_cfa < MIN_CRITICAL_FIELD_ACCURACY:
        violations.append(
            f"  ✗ critical_field_accuracy: {cand_cfa:.3f} < {MIN_CRITICAL_FIELD_ACCURACY:.2f}"
        )

    # 4. decision_accuracy regression
    cand_da = candidate.get("decision_accuracy", 0.0)
    base_da = baseline.get("decision_accuracy", 0.0)
    da_floor = base_da - MAX_DECISION_ACCURACY_DROP
    drop = MAX_DECISION_ACCURACY_DROP
    if cand_da < da_floor:
        violations.append(
            f"  ✗ decision_accuracy: {cand_da:.3f} < {da_floor:.3f} (baseline-{drop:.2f})"
        )

    return len(violations) == 0, violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate a candidate prompt version for promotion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--candidate", required=True, help="Path to candidate scorecard JSON")
    parser.add_argument("--baseline", required=True, help="Path to baseline scorecard JSON")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    candidate = _load(args.candidate)
    baseline = _load(args.baseline)

    cand_id = candidate.get("prompt_version_id", "?")
    base_id = baseline.get("prompt_version_id", "?")

    if not args.quiet:
        print(f"\n=== eval.gate: {cand_id} vs {base_id} ===\n")

    passed, violations = run_gate(candidate, baseline)

    if passed:
        if not args.quiet:
            print(f"  ✓ All rules passed — {cand_id} may be promoted.\n")
        return 0
    else:
        if not args.quiet:
            print(f"  PROMOTION BLOCKED for {cand_id}:\n")
            for v in violations:
                print(v)
            print()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
