"""Decide whether a candidate prompt/policy version may be promoted.

Usage:
    uv run python -m eval.gate --candidate <id> --baseline production

Promotion rules — fail (exit != 0) if ANY holds:
    - false_auto_approve_rate > baseline + 1%
    - cost/doc            > baseline + 20%
    - supplier_name_accuracy < 97%
    - human_override_rate worsens on critical slices

Scaffold stage: argument surface only. The gate logic lands in Phase 3.
"""

from __future__ import annotations

import argparse

# Thresholds kept here so the gate and the docs never drift.
MAX_FALSE_AUTO_APPROVE_DELTA = 0.01
MAX_COST_PER_DOC_DELTA_RATIO = 0.20
MIN_SUPPLIER_NAME_ACCURACY = 0.97


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate a candidate version for promotion.")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline", default="production")
    parser.parse_args()
    raise SystemExit("eval.gate lands in Phase 3 (LLMOps layer)")


if __name__ == "__main__":
    raise SystemExit(main())
