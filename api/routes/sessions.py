"""Session creation + state snapshot + observability (cost + trace + replay)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from core.db.repositories import SessionRepository, TraceRepository
from core.db.session import get_db
from observability.cost_meter import get_cost_snapshot, list_recent_sessions
from observability.replay import replay_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    entry_point: str = "plan_from_brief"


class SessionResponse(BaseModel):
    id: UUID
    entry_point: str
    started_at: datetime
    ended_at: datetime | None
    cost_usd: Decimal
    status: str


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(req: CreateSessionRequest, db: DbSession = Depends(get_db)) -> SessionResponse:
    repo = SessionRepository(db)
    row = repo.create(entry_point=req.entry_point)
    db.commit()
    return SessionResponse(
        id=row.id,
        entry_point=row.entry_point,
        started_at=row.started_at,
        ended_at=row.ended_at,
        cost_usd=row.cost_usd,
        status=row.status,
    )


@router.get("/recent")
def get_recent_sessions(limit: int = 20) -> list[dict]:
    return list_recent_sessions(limit=limit)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: UUID, db: DbSession = Depends(get_db)) -> SessionResponse:
    repo = SessionRepository(db)
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionResponse(
        id=row.id,
        entry_point=row.entry_point,
        started_at=row.started_at,
        ended_at=row.ended_at,
        cost_usd=row.cost_usd,
        status=row.status,
    )


class CostSnapshotResponse(BaseModel):
    session_id: UUID
    cost_usd: Decimal
    n_trace_events: int
    n_cache_hits: int
    n_errors: int
    cache_hit_rate: float
    total_tokens_in: int
    total_tokens_out: int
    total_latency_ms: int
    last_agent: str | None
    status: str


@router.get("/{session_id}/cost", response_model=CostSnapshotResponse)
def get_session_cost(session_id: UUID) -> CostSnapshotResponse:
    snap = get_cost_snapshot(session_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="session not found")
    return CostSnapshotResponse(
        session_id=snap.session_id,
        cost_usd=snap.cost_usd,
        n_trace_events=snap.n_trace_events,
        n_cache_hits=snap.n_cache_hits,
        n_errors=snap.n_errors,
        cache_hit_rate=snap.cache_hit_rate(),
        total_tokens_in=snap.total_tokens_in,
        total_tokens_out=snap.total_tokens_out,
        total_latency_ms=snap.total_latency_ms,
        last_agent=snap.last_agent,
        status=snap.status,
    )


@router.get("/{session_id}/trace")
def get_session_trace(session_id: UUID, db: DbSession = Depends(get_db)) -> list[dict]:
    events = TraceRepository(db).list_for_session(session_id)
    return [
        {
            "id": str(e.id),
            "agent_name": e.agent_name,
            "prompt_name": e.prompt_name,
            "prompt_version": e.prompt_version,
            "cache_hit": bool(e.cache_hit),
            "latency_ms": int(e.latency_ms or 0),
            "tokens_in": int(e.tokens_in or 0),
            "tokens_out": int(e.tokens_out or 0),
            "cost_usd": float(e.cost_usd or 0),
            "error": e.error,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


@router.get("/{session_id}/replay")
def get_session_replay(session_id: UUID) -> list[dict]:
    steps = replay_session(session_id)
    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "agent_name": s.agent_name,
            "prompt_name": s.prompt_name,
            "cache_hit": s.cache_hit,
            "latency_ms": s.latency_ms,
            "cost_usd": float(s.cost_usd),
            "tokens_in": s.tokens_in,
            "tokens_out": s.tokens_out,
            "error": s.error,
        }
        for s in steps
    ]
