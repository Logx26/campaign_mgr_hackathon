"""Trace event logger — writes one row per LLM/agent call to Postgres.

Every gateway call ends here. The Streamlit observability page reads these rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from core.db.repositories import TraceRepository
from core.db.session import SessionLocal


def log_event(
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
) -> None:
    """Persist a TraceEvent row. Swallows exceptions — observability must never break the call site."""
    try:
        with SessionLocal() as db:
            repo = TraceRepository(db)
            repo.log(
                session_id=session_id,
                agent_name=agent_name,
                input_hash=input_hash,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                output_size=output_size,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                error=error,
            )
            db.commit()
    except Exception:
        # Never let trace logging crash a real call. Surface via app logs only.
        import logging

        logging.getLogger("observability.trace").exception("trace log failed")


@contextmanager
def stopwatch():
    """Yields a callable returning elapsed_ms since the context start."""
    start = perf_counter()

    def elapsed_ms() -> int:
        return int((perf_counter() - start) * 1000)

    yield elapsed_ms
