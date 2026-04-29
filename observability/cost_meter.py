"""Live cost summary for a session — used by the Streamlit cost meter component.

Reads the session row + per-trace events. Returns aggregates the UI can poll without
caring about the trace schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from core.db import models
from core.db.repositories import SessionRepository, TraceRepository
from core.db.session import SessionLocal


@dataclass(slots=True)
class SessionCostSnapshot:
    session_id: UUID
    cost_usd: Decimal
    n_trace_events: int
    n_cache_hits: int
    n_errors: int
    total_tokens_in: int
    total_tokens_out: int
    total_latency_ms: int
    last_agent: str | None
    status: str

    def cache_hit_rate(self) -> float:
        if self.n_trace_events == 0:
            return 0.0
        return self.n_cache_hits / self.n_trace_events


def get_cost_snapshot(session_id: UUID) -> SessionCostSnapshot | None:
    """Build a snapshot of session-level cost + trace metrics. Returns None if session is unknown."""
    with SessionLocal() as db:
        row = SessionRepository(db).get(session_id)
        if row is None:
            return None
        events = TraceRepository(db).list_for_session(session_id)
        return SessionCostSnapshot(
            session_id=session_id,
            cost_usd=row.cost_usd or Decimal("0"),
            n_trace_events=len(events),
            n_cache_hits=sum(1 for e in events if e.cache_hit),
            n_errors=sum(1 for e in events if e.error),
            total_tokens_in=sum(int(e.tokens_in or 0) for e in events),
            total_tokens_out=sum(int(e.tokens_out or 0) for e in events),
            total_latency_ms=sum(int(e.latency_ms or 0) for e in events),
            last_agent=events[-1].agent_name if events else None,
            status=row.status,
        )


def list_recent_sessions(limit: int = 20) -> list[dict]:
    """Return the most-recent sessions with rolled-up trace counts. Used by /sessions/recent."""
    with SessionLocal() as db:
        rows = (
            db.query(models.Session)
            .order_by(models.Session.started_at.desc())
            .limit(limit)
            .all()
        )
        out: list[dict] = []
        for r in rows:
            n_events = (
                db.query(models.TraceEvent)
                .filter(models.TraceEvent.session_id == r.id)
                .count()
            )
            out.append(
                {
                    "id": str(r.id),
                    "entry_point": r.entry_point,
                    "started_at": r.started_at.isoformat(),
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                    "cost_usd": float(r.cost_usd or 0),
                    "status": r.status,
                    "n_trace_events": n_events,
                }
            )
        return out
