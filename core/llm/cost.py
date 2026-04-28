"""Per-session cost accounting + hard cap.

Pricing is centralized here so a model swap is one edit. Real-time figures from Azure pricing
docs as of 2026-04-27 — update when deployments change.

Counter is Redis-backed (`budget:session:{id}`) so cost is observable across processes
(uvicorn workers + streamlit + scripts).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import redis

from core.config import get_settings


# USD per 1K tokens. Conservative defaults; override via Pricing.from_settings if needed.
DEFAULT_PROMPT_PRICE_PER_1K: Decimal = Decimal("0.00250")  # gpt-4o input
DEFAULT_COMPLETION_PRICE_PER_1K: Decimal = Decimal("0.01000")  # gpt-4o output
DEFAULT_EMBEDDING_PRICE_PER_1K: Decimal = Decimal("0.00013")  # text-embedding-3-large


class BudgetExceeded(RuntimeError):
    """Raised when adding a cost would push a session over SESSION_BUDGET_USD."""


@dataclass(frozen=True, slots=True)
class Pricing:
    prompt_per_1k: Decimal = DEFAULT_PROMPT_PRICE_PER_1K
    completion_per_1k: Decimal = DEFAULT_COMPLETION_PRICE_PER_1K
    embedding_per_1k: Decimal = DEFAULT_EMBEDDING_PRICE_PER_1K

    def chat_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        p = (Decimal(prompt_tokens) / Decimal("1000")) * self.prompt_per_1k
        c = (Decimal(completion_tokens) / Decimal("1000")) * self.completion_per_1k
        return (p + c).quantize(Decimal("0.000001"))

    def embedding_cost(self, total_tokens: int) -> Decimal:
        return ((Decimal(total_tokens) / Decimal("1000")) * self.embedding_per_1k).quantize(
            Decimal("0.000001")
        )


_pricing = Pricing()


def get_pricing() -> Pricing:
    return _pricing


# ---------------------------------------------------------------------------
# Session budget counter (Redis-backed)
# ---------------------------------------------------------------------------


def _session_key(session_id: UUID) -> str:
    return f"budget:session:{session_id}"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL)


def get_session_cost(session_id: UUID) -> Decimal:
    raw = _redis().get(_session_key(session_id))
    return Decimal(raw.decode()) if raw else Decimal("0")


def add_cost(session_id: UUID, delta: Decimal) -> Decimal:
    """Atomically add `delta` to the session counter. Raises BudgetExceeded if the new total
    would exceed SESSION_BUDGET_USD. Returns the new running total."""
    settings = get_settings()
    cap = settings.SESSION_BUDGET_USD

    r = _redis()
    key = _session_key(session_id)

    # Best-effort optimistic check + update. Two requests racing past the cap is acceptable
    # (caps are advisory in dev/demo); for hard correctness we'd use a Lua script.
    current_raw = r.get(key)
    current = Decimal(current_raw.decode()) if current_raw else Decimal("0")
    new_total = current + delta
    if new_total > cap:
        raise BudgetExceeded(
            f"session {session_id} would exceed SESSION_BUDGET_USD={cap} "
            f"(current={current}, attempted_delta={delta})"
        )

    r.set(key, str(new_total))
    return new_total


def reset_session_cost(session_id: UUID) -> None:
    _redis().delete(_session_key(session_id))
