"""Session replay — re-execute a completed session against the cache for byte-identical output.

P8 Tier 0 ships a deterministic replay: walk the trace events in timestamp order, return
each event's metadata (agent, latency, cache_hit, cost). This lets the UI animate the
session "as it happened" without re-calling Azure.

Tier 1 will replay the actual graph nodes — every gateway call should be a cache hit,
which is what makes replay byte-identical. For Tier 0 the trace timeline is the demo;
the live cache is already deterministic when warmed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from core.db.repositories import TraceRepository
from core.db.session import SessionLocal


@dataclass(slots=True)
class ReplayStep:
    timestamp: datetime
    agent_name: str
    prompt_name: str | None
    cache_hit: bool
    latency_ms: int
    cost_usd: Decimal
    tokens_in: int
    tokens_out: int
    error: str | None


def replay_session(session_id: UUID) -> list[ReplayStep]:
    """Return ordered replay steps for a session. Empty list if no trace events."""
    with SessionLocal() as db:
        events = TraceRepository(db).list_for_session(session_id)
        return [
            ReplayStep(
                timestamp=e.timestamp,
                agent_name=e.agent_name,
                prompt_name=e.prompt_name,
                cache_hit=bool(e.cache_hit),
                latency_ms=int(e.latency_ms or 0),
                cost_usd=Decimal(e.cost_usd or 0),
                tokens_in=int(e.tokens_in or 0),
                tokens_out=int(e.tokens_out or 0),
                error=e.error,
            )
            for e in events
        ]
