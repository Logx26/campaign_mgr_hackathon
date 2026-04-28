"""Trace event persistence + read."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from core.db import models


class TraceRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        session_id: UUID,
        agent_name: str,
        input_hash: str,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        output_size: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: Decimal = Decimal("0"),
        latency_ms: int = 0,
        cache_hit: bool = False,
        error: str | None = None,
    ) -> models.TraceEvent:
        row = models.TraceEvent(
            session_id=session_id,
            agent_name=agent_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            input_hash=input_hash,
            output_size=output_size,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            error=error,
            timestamp=datetime.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_for_session(self, session_id: UUID) -> list[models.TraceEvent]:
        return list(
            self.db.query(models.TraceEvent)
            .filter(models.TraceEvent.session_id == session_id)
            .order_by(models.TraceEvent.timestamp.asc())
        )
