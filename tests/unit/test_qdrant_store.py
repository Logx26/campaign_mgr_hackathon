"""Qdrant wrapper — minimal smoke against the local Qdrant container."""
from __future__ import annotations

import os
import uuid

import pytest

from core.config import get_settings
from core.embeddings.qdrant_store import QdrantStore


pytestmark = pytest.mark.skipif(
    "QDRANT_URL" not in os.environ and not os.environ.get("CI_HAS_QDRANT"),
    reason="No Qdrant configured.",
)


def _vector(dim: int | None = None) -> list[float]:
    """Build a vector at the configured EMBEDDING_DIM so tests follow the live deployment."""
    return [0.001] * (dim if dim is not None else get_settings().EMBEDDING_DIM)


def test_collection_exists_for_seeded_briefs():
    store = QdrantStore()
    assert store.collection_exists("briefs_v1")


def test_upsert_and_search_round_trip():
    store = QdrantStore()
    pid = str(uuid.uuid4())
    vec = _vector()
    store.upsert("briefs_v1", pid, vec, payload={"campaign_name": "smoke"})
    hits = store.search("briefs_v1", vec, top_k=3)
    assert any(h.point_id == pid for h in hits)
    store.delete("briefs_v1", [pid])
