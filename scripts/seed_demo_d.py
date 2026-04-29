"""Demo D — W3 multi-asset consistency. Pre-stages the 5 sample assets in Redis.

Re-running is safe: same key, refreshed TTL. The launcher reads `demo:d:payload`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def seed() -> dict:
    from orchestrator.interrupts import _redis

    asset_dir = _PROJECT_ROOT / "seeds" / "sample_assets"
    assets = []
    for path in sorted(asset_dir.glob("asset_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        body = (data.get("body") or "").strip()
        if not body:
            continue
        assets.append(
            {
                "body": body,
                "source_name": data.get("source_name"),
                "channel": data.get("channel"),
                "audience_hint": data.get("audience_hint"),
            }
        )

    try:
        r = _redis()
        r.setex("demo:d:payload", 86400, json.dumps({"assets": assets}))
        r.setex("demo:d:armed", 86400, "1")
        status = "armed"
    except Exception as exc:
        status = f"redis-unavailable: {exc}"
    return {"status": status, "n_assets": len(assets)}


if __name__ == "__main__":
    out = seed()
    print(json.dumps(out, indent=2))
