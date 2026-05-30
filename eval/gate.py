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
from pathlib import Path

# Thresholds as named constants — same values used in the promote API endpoint.
MAX_FALSE_AUTO_APPROVE_DELTA = 0.01  # +1pp
MAX_COST_PER_DOC_DELTA_RATIO = 0.20  # +20%
MIN_CRITICAL_FIELD_ACCURACY = 0.85  # total_amount + tax_id_cnpj + document_number
MAX_DECISION_ACCURACY_DROP = 0.05  # -5pp


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
