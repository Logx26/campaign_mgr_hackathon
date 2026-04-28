"""Cost meter — pricing math + session cap enforcement."""
from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest

from core.llm.cost import BudgetExceeded, Pricing, add_cost, get_session_cost, reset_session_cost


def test_pricing_chat_cost_math():
    p = Pricing(prompt_per_1k=Decimal("0.001"), completion_per_1k=Decimal("0.002"))
    cost = p.chat_cost(prompt_tokens=1000, completion_tokens=500)
    # 1*0.001 + 0.5*0.002 = 0.001 + 0.001 = 0.002
    assert cost == Decimal("0.002000")


def test_pricing_embedding_cost_math():
    p = Pricing(embedding_per_1k=Decimal("0.0001"))
    assert p.embedding_cost(2000) == Decimal("0.000200")


@pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured.",
)
def test_session_cost_accumulator_and_cap(monkeypatch):
    sid = uuid4()
    reset_session_cost(sid)
    assert get_session_cost(sid) == Decimal("0")

    # Cap is normally read from settings; force it tiny via monkeypatching get_settings.
    from core.config import Settings
    from core.llm import cost as cost_mod

    fake = Settings.model_construct(  # bypass env, build minimal settings
        AZURE_OPENAI_API_KEY=__import__("pydantic").SecretStr("x"),
        AZURE_OPENAI_ENDPOINT="https://x/",
        AZURE_OPENAI_DEPLOYMENT="gpt-4o",
        AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT="text-embedding-3-large",
        AZURE_OPENAI_API_VERSION="2024-08-01-preview",
        POSTGRES_DSN="postgresql+psycopg://hackuser:hackpass@localhost:5432/hackdb",
        QDRANT_URL="http://localhost:6333",
        REDIS_URL=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        LLM_CACHE_TTL_SECONDS=60,
        SESSION_BUDGET_USD=Decimal("0.0001"),
        APP_ENV="test",
        EMBEDDING_DIM=1536,
        API_BASE_URL="http://localhost:8000",
    )
    monkeypatch.setattr(cost_mod, "get_settings", lambda: fake)

    add_cost(sid, Decimal("0.00005"))
    assert get_session_cost(sid) == Decimal("0.00005")

    with pytest.raises(BudgetExceeded):
        add_cost(sid, Decimal("0.001"))

    reset_session_cost(sid)
