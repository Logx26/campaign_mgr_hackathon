"""LLM gateway — mocked Azure response paths."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from core.llm import gateway as gw
from core.llm.cache import cache_clear_namespace


class Ping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str
    count: int


def _fake_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured (gateway uses cache).",
)
@pytest.mark.asyncio
async def test_call_structured_parses_response_and_writes_cache(monkeypatch):
    cache_clear_namespace("llm:cache:")

    async def fake_invoke(**kwargs):
        return _fake_response('{"reply":"hi","count":1}')

    monkeypatch.setattr(gw, "_invoke_with_retry", fake_invoke)
    monkeypatch.setattr(gw, "_try_add_cost", lambda *_a, **_k: None)
    monkeypatch.setattr(gw, "log_event", lambda **_kw: None)

    out = await gw.call_structured(
        prompt_name="_smoke",
        variables={},
        output_schema=Ping,
        session_id=uuid4(),
    )
    assert isinstance(out, Ping)
    assert out.reply == "hi"
    assert out.count == 1


@pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured.",
)
@pytest.mark.asyncio
async def test_call_structured_cache_hit_avoids_invoke(monkeypatch):
    cache_clear_namespace("llm:cache:")

    calls = {"n": 0}

    async def fake_invoke(**kwargs):
        calls["n"] += 1
        return _fake_response('{"reply":"first","count":2}')

    monkeypatch.setattr(gw, "_invoke_with_retry", fake_invoke)
    monkeypatch.setattr(gw, "_try_add_cost", lambda *_a, **_k: None)
    monkeypatch.setattr(gw, "log_event", lambda **_kw: None)

    sid = uuid4()
    await gw.call_structured(
        prompt_name="_smoke", variables={}, output_schema=Ping, session_id=sid
    )
    out2 = await gw.call_structured(
        prompt_name="_smoke", variables={}, output_schema=Ping, session_id=sid
    )
    assert calls["n"] == 1, "second call must be cache hit"
    assert out2.reply == "first"


@pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured.",
)
@pytest.mark.asyncio
async def test_call_structured_repairs_invalid_json_then_succeeds(monkeypatch):
    cache_clear_namespace("llm:cache:")

    state = {"calls": 0}

    async def fake_invoke(**kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            return _fake_response("not json at all")
        return _fake_response('{"reply":"ok","count":3}')

    monkeypatch.setattr(gw, "_invoke_with_retry", fake_invoke)
    monkeypatch.setattr(gw, "_try_add_cost", lambda *_a, **_k: None)
    monkeypatch.setattr(gw, "log_event", lambda **_kw: None)

    out = await gw.call_structured(
        prompt_name="_smoke", variables={}, output_schema=Ping, session_id=uuid4()
    )
    assert state["calls"] == 2
    assert out.reply == "ok"


@pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured.",
)
@pytest.mark.asyncio
async def test_call_structured_raises_after_two_bad_responses(monkeypatch):
    cache_clear_namespace("llm:cache:")

    async def fake_invoke(**kwargs):
        return _fake_response("still not json")

    monkeypatch.setattr(gw, "_invoke_with_retry", fake_invoke)
    monkeypatch.setattr(gw, "_try_add_cost", lambda *_a, **_k: None)
    monkeypatch.setattr(gw, "log_event", lambda **_kw: None)

    with pytest.raises(gw.StructuredOutputParseError):
        await gw.call_structured(
            prompt_name="_smoke",
            variables={"x": "unique"},  # avoid hitting an existing cache entry
            output_schema=Ping,
            session_id=uuid4(),
        )
