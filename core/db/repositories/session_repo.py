"""Orchestrator session metadata."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from core.db import models


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entry_point: str) -> models.Session:
        row = models.Session(id=uuid4(), entry_point=entry_point, started_at=datetime.utcnow())
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, session_id: UUID) -> models.Session | None:
        return self.db.get(models.Session, session_id)

    def add_cost(self, session_id: UUID, cost: Decimal) -> None:
        row = self.db.get(models.Session, session_id)
        if row is not None:
            row.cost_usd = (row.cost_usd or Decimal("0")) + cost
            self.db.flush()

    def end(self, session_id: UUID, status: str = "complete") -> None:
        row = self.db.get(models.Session, session_id)
        if row is not None:
            row.ended_at = datetime.utcnow()
            row.status = status
            self.db.flush()
