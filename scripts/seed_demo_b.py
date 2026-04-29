"""Demo B — kickoff (the one judges see first). Sample Brief A: ambiguous, 3+ clarifications expected.

Same idempotent shape as seed_demo_a — match by raw_source, return the existing demo if present.
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


DEMO_B_BRIEF_PATH = _PROJECT_ROOT / "seeds" / "exemplar_briefs" / "b2b_saas_q3_enterprise.md"


def seed() -> dict:
    from core.db import models
    from core.db.session import SessionLocal

    raw = DEMO_B_BRIEF_PATH.read_text(encoding="utf-8")
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
            parsed_json={},
        )
        db.add(brief)
        db.commit()
        return {"session_id": str(sess.id), "brief_id": str(brief.id), "status": "created"}


if __name__ == "__main__":
    out = seed()
    import json as _json
    print(_json.dumps(out, indent=2))
