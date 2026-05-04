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
    """Build a snapshot of session-level cost + trace metrics. Returns None if session is unknown.

    Cost is computed as SUM(trace_events.cost_usd) for the session — `sessions.cost_usd`
    is a Redis-driven counter (`core/llm/cost.py:add_cost`) that is not always written
    back to Postgres, so reading it directly under-reported live cost. The trace rows
    are the authoritative ledger of every paid call (cache hits land at $0, which is
    correct), so summing them gives the meter that judges expect to see ticking.
    """
    with SessionLocal() as db:
        row = SessionRepository(db).get(session_id)
        if row is None:
            return None
        events = TraceRepository(db).list_for_session(session_id)
        # Authoritative cost = sum of trace event costs.
        events_cost = sum((Decimal(e.cost_usd or 0) for e in events), Decimal("0"))
        # Keep `sessions.cost_usd` as a denormalized convenience: if it was written and
        # matches roughly, prefer the events sum; if events sum is zero but the column
        # has a value (legacy sessions), surface the column value instead.
        cost_display = events_cost if events_cost > 0 else (row.cost_usd or Decimal("0"))
        return SessionCostSnapshot(
            session_id=session_id,
            cost_usd=cost_display,
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
    """Return the most-recent sessions with rolled-up trace counts and cost.

    Cost is computed as `SUM(trace_events.cost_usd)` for each session — the
    same authoritative path `get_cost_snapshot` uses. Reading
    `sessions.cost_usd` directly leaves the dropdown stuck at $0.0000 because
    that column is rarely written (the trace events have the real ledger).
    Falls back to the session row's stored value only when no events exist."""
    with SessionLocal() as db:
        rows = (
            db.query(models.Session)
            .order_by(models.Session.started_at.desc())
            .limit(limit)
            .all()
        )
        out: list[dict] = []
        for r in rows:
            events = (
                db.query(models.TraceEvent)
                .filter(models.TraceEvent.session_id == r.id)
                .all()
            )
            n_events = len(events)
            events_cost = sum(
                (Decimal(e.cost_usd or 0) for e in events), Decimal("0")
            )
            cost_display = (
                events_cost if events_cost > 0 else (r.cost_usd or Decimal("0"))
            )
            out.append(
                {
                    "id": str(r.id),
                    "entry_point": r.entry_point,
                    "started_at": r.started_at.isoformat(),
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                    "cost_usd": float(cost_display),
                    "status": r.status,
                    "n_trace_events": n_events,
                }
            )
        return out
