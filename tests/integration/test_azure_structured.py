"""Live Azure OpenAI integration tests.

Each test hits Azure once with a tiny schema. Total cost is well under 1¢.
Skipped automatically when AZURE_OPENAI_* env is not configured.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from core.config import get_settings
from core.db import models
from core.db.session import SessionLocal
from core.llm import gateway as gw
from core.llm.cache import cache_clear_namespace
from core.llm.cost import get_session_cost, reset_session_cost


pytestmark = pytest.mark.integration


def _has_azure_chat() -> bool:
    s = get_settings()
    return bool(
        s.AZURE_OPENAI_API_KEY
        and s.AZURE_OPENAI_ENDPOINT
        and s.AZURE_OPENAI_DEPLOYMENT
    )


class Ping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str
    count: int


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_real_structured_call_returns_parsed_pydantic():
    cache_clear_namespace("llm:cache:")
    sid = uuid4()
    reset_session_cost(sid)

    out = await gw.call_structured(
        prompt_name="_smoke",
        variables={},
        output_schema=Ping,
        session_id=sid,
        use_cache=False,
    )
    assert isinstance(out, Ping)
    assert isinstance(out.reply, str) and len(out.reply) > 0
    assert isinstance(out.count, int)


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_real_call_then_cache_hit():
    cache_clear_namespace("llm:cache:")
    sid = uuid4()
    reset_session_cost(sid)

    first = await gw.call_structured(
        prompt_name="_smoke",
        variables={"k": "cache_test"},
        output_schema=Ping,
        session_id=sid,
    )
    cost_after_first = get_session_cost(sid)

    second = await gw.call_structured(
        prompt_name="_smoke",
        variables={"k": "cache_test"},
        output_schema=Ping,
        session_id=sid,
    )
    cost_after_second = get_session_cost(sid)

    # Same parsed content + cost did not increase = cache hit.
    assert second.model_dump() == first.model_dump()
    assert cost_after_second == cost_after_first


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_real_call_writes_trace_row():
    cache_clear_namespace("llm:cache:")
    sid = uuid4()
    reset_session_cost(sid)

    await gw.call_structured(
        prompt_name="_smoke",
        variables={"trace_probe": str(sid)},
        output_schema=Ping,
        session_id=sid,
        use_cache=False,
    )

    with SessionLocal() as db:
        rows = db.execute(
            select(models.TraceEvent).where(models.TraceEvent.session_id == sid)
        ).scalars().all()
    assert len(rows) >= 1
    assert any(not r.cache_hit and r.tokens_in > 0 for r in rows)
