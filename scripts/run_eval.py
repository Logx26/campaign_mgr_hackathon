"""Run the full eval golden set and print the summary metrics.

Usage:
    python scripts/run_eval.py [--tag <name>] [--with-plan]

`--with-plan` runs `generate_plan` on items that supply `expected_plan_shape.yaml`.
By default we score gap-catch only — plan generation is much slower (3 LLM calls per
channel) and not every golden item has plan-shape expectations yet.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make the project root importable when run as a CLI from repo root.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.runner import run_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full eval golden set.")
    parser.add_argument("--tag", default=None, help="Optional tag for the EvalRun row.")
    parser.add_argument(
        "--with-plan",
        action="store_true",
        help="Also run plan generation + score plan_completeness on items that supply expectations.",
    )
    args = parser.parse_args()

    result = asyncio.run(run_all(tag=args.tag, with_plan=args.with_plan))
    print(json.dumps({"run_id": str(result.run_id), "summary": result.summary}, indent=2))

    s = result.summary
    if s.get("items_total", 0) == 0:
        print("WARN: golden set is empty.", file=sys.stderr)
        return 0
    if s.get("items_errored", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
