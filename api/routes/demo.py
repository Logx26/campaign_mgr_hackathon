"""Demo launcher helpers — Redis arm checks + fallback payload retrieval."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/armed")
def demo_armed(key: str) -> dict:
    """Returns {armed: bool} given a Redis marker key (e.g. 'demo:c:armed')."""
    if not key.startswith("demo:"):
        raise HTTPException(status_code=400, detail="key must start with 'demo:'")
    try:
        from orchestrator.interrupts import _redis
        v = _redis().get(key)
        return {"armed": v is not None, "key": key}
    except Exception:
        return {"armed": False, "key": key}


@router.get("/payload")
def demo_payload(key: str) -> dict:
    """Returns the cached payload for a demo (used by W2 / W3 demo loads).

    Allowed keys: demo:c:payload, demo:d:payload.
    """
    if key not in {"demo:c:payload", "demo:d:payload"}:
        raise HTTPException(status_code=400, detail="unknown demo payload key")
    try:
        from orchestrator.interrupts import _redis
        raw = _redis().get(key)
        if raw is None:
            raise HTTPException(status_code=404, detail="payload not armed — run the seed script")
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc
