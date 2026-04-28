"""Azure embeddings client with Redis cache.

Embeddings deployment may not exist yet at the time of authoring (P2). The client validates
its deployment lazily on the first real call. `is_embeddings_available()` lets callers + tests
gate live use without hardcoding env knowledge.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from openai import AsyncAzureOpenAI

from core.config import get_settings
from core.llm.cache import embedding_get, embedding_set, make_embedding_key
from core.llm.cost import add_cost, get_pricing
from observability.trace import log_event, stopwatch


class EmbeddingsUnavailable(RuntimeError):
    """Raised when the Azure embeddings deployment is not configured / not reachable."""


def _client() -> AsyncAzureOpenAI:
    s = get_settings()
    return AsyncAzureOpenAI(
        api_key=s.AZURE_OPENAI_API_KEY.get_secret_value(),
        api_version=s.AZURE_OPENAI_API_VERSION,
        azure_endpoint=s.AZURE_OPENAI_ENDPOINT,
    )


def is_embeddings_available() -> bool:
    """True iff a deployment name is set. Does not perform a network call."""
    name = (get_settings().AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT or "").strip()
    return bool(name)


_PROBE_RESULT: bool | None = None


async def probe_embeddings_deployment() -> bool:
    """Live probe — attempt one tiny embedding call, cache the result for the process.

    Returns True if the deployment exists and answers; False if it 404s (DeploymentNotFound)
    or any other error. Use this in tests / startup checks where you need certainty
    beyond `is_embeddings_available()` (which only checks env presence).
    """
    global _PROBE_RESULT
    if _PROBE_RESULT is not None:
        return _PROBE_RESULT
    if not is_embeddings_available():
        _PROBE_RESULT = False
        return False
    try:
        await embed_one("ping", use_cache=False)
        _PROBE_RESULT = True
    except Exception:
        _PROBE_RESULT = False
    return _PROBE_RESULT


def reset_embeddings_probe() -> None:
    """Test hook — clear the cached probe result."""
    global _PROBE_RESULT
    _PROBE_RESULT = None


async def embed_one(
    text: str,
    *,
    session_id: UUID | None = None,
    use_cache: bool = True,
) -> list[float]:
    """Embed a single text. Cached by (model, text)."""
    settings = get_settings()
    if not is_embeddings_available():
        raise EmbeddingsUnavailable(
            "AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT is not set; cannot call embeddings."
        )

    model = settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT
    cache_key = make_embedding_key(text, model)

    if use_cache:
        cached = embedding_get(cache_key)
        if cached is not None:
            return cached

    client = _client()
    with stopwatch() as elapsed:
        try:
            resp = await client.embeddings.create(model=model, input=text)
        except Exception as exc:
            if session_id is not None:
                log_event(
                    session_id=session_id,
                    agent_name="embeddings",
                    input_hash=cache_key.split(":")[-1],
                    latency_ms=elapsed(),
                    error=f"{type(exc).__name__}: {exc}",
                )
            raise

        vector = resp.data[0].embedding
        tokens = getattr(resp.usage, "total_tokens", 0) or 0
        cost = get_pricing().embedding_cost(tokens)

    if use_cache:
        embedding_set(cache_key, vector)

    if session_id is not None:
        try:
            add_cost(session_id, cost)
        except Exception:
            pass
        log_event(
            session_id=session_id,
            agent_name="embeddings",
            input_hash=cache_key.split(":")[-1],
            output_size=len(vector),
            tokens_in=tokens,
            cost_usd=Decimal(cost),
            latency_ms=elapsed(),
        )

    return vector


async def embed_many(
    texts: list[str],
    *,
    session_id: UUID | None = None,
    use_cache: bool = True,
    concurrency: int = 8,
) -> list[list[float]]:
    """Embed multiple texts with bounded concurrency."""
    if not texts:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def _one(t: str) -> list[float]:
        async with sem:
            return await embed_one(t, session_id=session_id, use_cache=use_cache)

    return await asyncio.gather(*[_one(t) for t in texts])
