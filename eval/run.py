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


def _post_scorecard(
    api_url: str,
    token: str,
    prompt_id: str,
    scorecard: dict,
    quiet: bool,
) -> bool:
    """POST scorecard to PATCH /api/v1/prompts/{id}/scorecard. Returns True on success."""
    import urllib.request

    url = f"{api_url.rstrip('/')}/api/v1/prompts/{prompt_id}/scorecard"
    payload = json.dumps({"scorecard": scorecard}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if not quiet:
                print(f"Scorecard saved to DB (HTTP {resp.status})", file=sys.stderr)
            return True
    except Exception as exc:
        print(f"ERROR: could not save scorecard to DB: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LedgerCopilot eval.")
    parser.add_argument("--dataset", default="eval/dataset", help="Path to dataset root")
    parser.add_argument("--prompt-version", default="dev", help="Prompt alias or version id")
    parser.add_argument("--out", default=None, help="Write scorecard JSON to this file")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument(
        "--post-scorecard",
        metavar="PROMPT_ID",
        default=None,
        help="After eval, PATCH the scorecard to the API for this prompt version UUID",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the LedgerCopilot API (used with --post-scorecard)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for API auth (used with --post-scorecard)",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: dataset path not found: {dataset_path}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"Running eval against {dataset_path} with prompt={args.prompt_version}",
            file=sys.stderr,
        )

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

    if args.post_scorecard:
        if not args.token:
            print("ERROR: --token is required when using --post-scorecard", file=sys.stderr)
            return 1
        ok = _post_scorecard(args.api_url, args.token, args.post_scorecard, sc_dict, args.quiet)
        if not ok:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
