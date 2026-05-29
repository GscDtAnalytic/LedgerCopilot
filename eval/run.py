"""Run a prompt version against the eval dataset and emit a scorecard.

Usage:
    uv run python -m eval.run --dataset eval/dataset --prompt-version <id>

Scaffold stage: argument surface only. The runner lands in Phase 3.
"""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LedgerCopilot eval.")
    parser.add_argument("--dataset", default="eval/dataset")
    parser.add_argument("--prompt-version", required=True)
    parser.parse_args()
    raise SystemExit("eval.run lands in Phase 3 (LLMOps layer)")


if __name__ == "__main__":
    raise SystemExit(main())
