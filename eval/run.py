"""Run a prompt version against the eval dataset and emit a scorecard.

Usage:
    uv run python -m eval.run --dataset eval/dataset --prompt-version dev

Output: scorecard JSON written to stdout (pipe to a file, or use --out).
The scorecard is also the input to eval.gate for promotion decisions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from eval.runner import run_eval


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LedgerCopilot eval.")
    parser.add_argument("--dataset", default="eval/dataset", help="Path to dataset root")
    parser.add_argument("--prompt-version", default="dev", help="Prompt alias or version id")
    parser.add_argument("--out", default=None, help="Write scorecard JSON to this file")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: dataset path not found: {dataset_path}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Running eval against {dataset_path} with prompt={args.prompt_version}",
              file=sys.stderr)

    scorecard = asyncio.run(
        run_eval(dataset_root=dataset_path, prompt_version_id=args.prompt_version)
    )
    sc_dict = scorecard.as_dict()

    output = json.dumps(sc_dict, indent=2)

    if args.out:
        Path(args.out).write_text(output)
        if not args.quiet:
            print(f"Scorecard written to {args.out}", file=sys.stderr)
    else:
        print(output)

    if not args.quiet:
        print(
            f"\nSummary: {scorecard.total_fixtures} fixtures · "
            f"field_accuracy={scorecard.exact_field_accuracy:.0%} · "
            f"false_auto_approve={scorecard.false_auto_approve_rate:.1%} · "
            f"supplier_name_acc={scorecard.supplier_name_accuracy:.0%} · "
            f"p95_latency={scorecard.p95_latency_ms:.0f}ms",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
