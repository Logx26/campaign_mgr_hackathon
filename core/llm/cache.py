"""Redis-backed cache for LLM and embedding responses.

Cache key includes prompt name + version + variables hash so prompt iterations naturally
invalidate. TTL is configurable via LLM_CACHE_TTL_SECONDS (default 1 hour).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import redis

from core.config import get_settings


_LLM_PREFIX = "llm:cache:"
_EMBED_PREFIX = "embeddings:cache:"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL)


def _stable_hash(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LLM response cache
# ---------------------------------------------------------------------------


def make_llm_key(
    prompt_name: str,
    prompt_version: str,
    variables: dict[str, Any] | None,
    schema_name: str | None = None,
) -> str:
    h = _stable_hash(prompt_name, prompt_version, variables or {}, schema_name or "")
    return f"{_LLM_PREFIX}{h}"


def llm_get(key: str) -> str | None:
    raw = _redis().get(key)
    return raw.decode("utf-8") if raw else None


def llm_set(key: str, value: str, ttl: int | None = None) -> None:
    ttl = ttl if ttl is not None else get_settings().LLM_CACHE_TTL_SECONDS
    _redis().setex(key, ttl, value)


# ---------------------------------------------------------------------------
# Embedding cache (text -> vector)
# ---------------------------------------------------------------------------


def make_embedding_key(text: str, model: str) -> str:
    return f"{_EMBED_PREFIX}{_stable_hash(model, text)}"


def embedding_get(key: str) -> list[float] | None:
    raw = _redis().get(key)
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))


def embedding_set(key: str, vector: list[float], ttl: int | None = None) -> None:
    ttl = ttl if ttl is not None else get_settings().LLM_CACHE_TTL_SECONDS * 24
    _redis().setex(key, ttl, json.dumps(vector))


def cache_clear_namespace(prefix: str = _LLM_PREFIX) -> int:
    """Test-only: delete keys matching prefix*. Returns count deleted."""
    r = _redis()
    deleted = 0
    for k in r.scan_iter(match=f"{prefix}*"):
        r.delete(k)
        deleted += 1
    return deleted
