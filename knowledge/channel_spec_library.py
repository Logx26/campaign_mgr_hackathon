"""Channel-spec convenience wrapper around `ChannelSpecRepository` + DB session."""
from __future__ import annotations

from core.db.repositories import ChannelSpecRepository
from core.db.session import SessionLocal


def list_channel_specs() -> list[dict]:
    """Return all seeded channel specs as plain dicts (suitable for prompt injection)."""
    with SessionLocal() as db:
        return [
            {"name": r.name, "version": r.version, **(r.spec_json or {})}
            for r in ChannelSpecRepository(db).list_all()
        ]


def get_channel_spec(name: str) -> dict | None:
    with SessionLocal() as db:
        row = ChannelSpecRepository(db).get_by_name(name)
        if row is None:
            return None
        return {"name": row.name, "version": row.version, **(row.spec_json or {})}
