"""Demo C — W2 standalone QA. Pre-stages the misaligned brief+plan pair from `seeds/qa_demo/`.

Result is consumed by ui/pages/0_demo_launcher.py — it reads the same files at click time.
This script just records that the demo is "armed" by writing a marker into Redis so the
launcher can show a "warmed" badge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def seed() -> dict:
    from orchestrator.interrupts import _redis  # reuses the project's Redis client helper

    qa_dir = _PROJECT_ROOT / "seeds" / "qa_demo"
    brief = (qa_dir / "brief.md").read_text(encoding="utf-8")
    plan = (qa_dir / "plan.json").read_text(encoding="utf-8")

    payload = {
        "brief_text": brief,
        "plan_json": json.loads(plan),
    }
    try:
        r = _redis()
        r.setex("demo:c:payload", 86400, json.dumps(payload))
        r.setex("demo:c:armed", 86400, "1")
        status = "armed"
    except Exception as exc:
        status = f"redis-unavailable: {exc}"
    return {"status": status, "brief_chars": len(brief), "plan_channels": len(payload["plan_json"].get("channels", []))}


if __name__ == "__main__":
    out = seed()
    print(json.dumps(out, indent=2))
