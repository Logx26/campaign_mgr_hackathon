"""Cache layer behavior — keys are stable across equivalent inputs and miss across changes."""
from __future__ import annotations

import os

import pytest

from core.llm.cache import (
    cache_clear_namespace,
    embedding_get,
    embedding_set,
    llm_get,
    llm_set,
    make_embedding_key,
    make_llm_key,
)


pytestmark = pytest.mark.skipif(
    "REDIS_URL" not in os.environ and not os.environ.get("CI_HAS_REDIS"),
    reason="No Redis configured; skipping cache tests. Set REDIS_URL or run with infra up.",
)


def test_llm_key_is_deterministic_across_equivalent_inputs():
    a = make_llm_key("clarifier", "v1", {"x": 1, "y": 2}, "GapList")
    b = make_llm_key("clarifier", "v1", {"y": 2, "x": 1}, "GapList")
    assert a == b


def test_llm_key_changes_on_version_bump():
    a = make_llm_key("clarifier", "v1", {"x": 1}, "GapList")
    b = make_llm_key("clarifier", "v2", {"x": 1}, "GapList")
    assert a != b


def test_llm_set_and_get_round_trip():
    key = make_llm_key("__test__", "v1", {"hello": "world"}, "X")
    cache_clear_namespace("llm:cache:")
    assert llm_get(key) is None
    llm_set(key, '{"ok":1}', ttl=60)
    assert llm_get(key) == '{"ok":1}'
    cache_clear_namespace("llm:cache:")


def test_embedding_set_and_get_round_trip():
    key = make_embedding_key("hello world", "text-embedding-3-large")
    embedding_set(key, [0.1, 0.2, 0.3], ttl=60)
    out = embedding_get(key)
    assert out == [0.1, 0.2, 0.3]
