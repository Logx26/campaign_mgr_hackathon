"""Demo A — happy path. A complete brief, no clarification needed.

Idempotent: re-running over the same DB updates the demo's brief in place by
matching `briefs.raw_source` (no UI dependency on stable IDs).

Usage:
    python scripts/seed_demo_a.py [--dsn ...]
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


DEMO_A_BRIEF_PATH = _PROJECT_ROOT / "seeds" / "golden_set" / "brief_002.md"


def seed() -> dict:
    """Insert (or update) Demo A's session + brief. Returns {session_id, brief_id}."""
    from core.db import models
    from core.db.session import SessionLocal

    raw = DEMO_A_BRIEF_PATH.read_text(encoding="utf-8")
    with SessionLocal() as db:
        existing = (
            db.query(models.Brief)
            .filter(models.Brief.raw_source == raw)
            .order_by(models.Brief.created_at.desc())
            .first()
        )
        if existing is not None:
            return {
                "session_id": str(existing.session_id) if existing.session_id else None,
                "brief_id": str(existing.id),
                "status": "exists",
            }

        sess = models.Session(id=uuid4(), entry_point="plan_from_brief")
        db.add(sess)
        db.flush()
        brief = models.Brief(
            id=uuid4(),
            session_id=sess.id,
            raw_source=raw,
            source_format="markdown",
            parsed_json={},  # populated when the user clicks Intake on the launcher
        )
        db.add(brief)
        db.commit()
        return {"session_id": str(sess.id), "brief_id": str(brief.id), "status": "created"}


if __name__ == "__main__":
    out = seed()
    import json as _json
    print(_json.dumps(out, indent=2))
