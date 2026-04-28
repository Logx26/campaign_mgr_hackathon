"""Session creation + state snapshot."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from core.db.repositories import SessionRepository
from core.db.session import get_db

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
