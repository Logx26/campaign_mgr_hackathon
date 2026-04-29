"""Terminology scanner — covers greedy cosine clustering math, no-embedding fallback,
and end-to-end run with monkey-patched dictionary + embeddings."""
from __future__ import annotations

import math
from uuid import uuid4

import pytest

from agents import terminology_scanner as ts


# -------- _cosine -----------------------------------------------------------


def test_cosine_orthogonal_returns_zero():
    assert ts._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0, abs=1e-9)


def test_cosine_identical_returns_one():
    assert ts._cosine([0.5, 0.5, 0.7], [0.5, 0.5, 0.7]) == pytest.approx(1.0, abs=1e-9)


def test_cosine_zero_vector_returns_zero_safely():
    assert ts._cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


# -------- cluster_terms -----------------------------------------------------


@pytest.mark.asyncio
async def test_cluster_terms_groups_high_similarity_pairs(monkeypatch):
    candidates = ["AI-powered", "AI-assisted", "revenue operations"]

    # Fake embeddings: powered + assisted are very close, revenue ops is orthogonal.
    async def fake_embed_many(texts, **_kwargs):
        return {
            "AI-powered": [1.0, 0.0, 0.05],
            "AI-assisted": [0.98, 0.0, 0.05],
            "revenue operations": [0.0, 1.0, 0.0],
        }[texts[0]] if False else [
            [1.0, 0.0, 0.05],
            [0.98, 0.0, 0.05],
            [0.0, 1.0, 0.0],
        ]

    monkeypatch.setattr(ts, "is_embeddings_available", lambda: True)
    monkeypatch.setattr(ts, "embed_many", fake_embed_many)

    clusters = await ts.cluster_terms(candidates, session_id=uuid4())
    # Two clusters: {AI-powered, AI-assisted} and {revenue operations}
    assert len(clusters) == 2
    pair = next(c for c in clusters if "AI-powered" in c)
    assert set(pair) == {"AI-powered", "AI-assisted"}


@pytest.mark.asyncio
async def test_cluster_terms_no_embeddings_falls_back_each_term_alone(monkeypatch):
    monkeypatch.setattr(ts, "is_embeddings_available", lambda: False)
    clusters = await ts.cluster_terms(["AI-powered", "AI-assisted", "revenue operations"])
    assert clusters == [["AI-powered"], ["AI-assisted"], ["revenue operations"]]


@pytest.mark.asyncio
async def test_cluster_terms_handles_embeddings_failure(monkeypatch):
    """Demo-stable fallback when Azure throttles."""
    monkeypatch.setattr(ts, "is_embeddings_available", lambda: True)

    async def boom(*_a, **_kw):
        raise RuntimeError("azure throttled")

    monkeypatch.setattr(ts, "embed_many", boom)
    clusters = await ts.cluster_terms(["a", "b"])
    assert clusters == [["a"], ["b"]]


# -------- TerminologyScanner.run -------------------------------------------


@pytest.mark.asyncio
async def test_scanner_emits_finding_for_drift_cluster(monkeypatch):
    """Two assets, three of which mention 'AI-powered' and two 'AI-assisted', should
    produce one TerminologyFinding with both variants."""
    asset_ids = [uuid4() for _ in range(5)]
    assets = [
        {"id": asset_ids[0], "body": "We sell an AI-powered reporting engine."},
        {"id": asset_ids[1], "body": "Our AI-powered platform is enterprise-grade."},
        {"id": asset_ids[2], "body": "AI-powered analytics, built for revenue ops."},
        {"id": asset_ids[3], "body": "An AI-assisted workflow keeps humans in the loop."},
        {"id": asset_ids[4], "body": "AI-assisted reporting for revenue operations leaders."},
    ]

    monkeypatch.setattr(
        ts,
        "_candidate_terms_from_dictionary",
        lambda: ["AI-powered", "AI-assisted", "revenue operations"],
    )
    monkeypatch.setattr(ts, "is_embeddings_available", lambda: True)

    async def fake_embed_many(texts, **_kwargs):
        # Map terms to vectors that make AI-powered and AI-assisted cluster together.
        v_map = {
            "AI-powered": [1.0, 0.0, 0.0],
            "AI-assisted": [0.95, 0.05, 0.0],
            "revenue operations": [0.0, 1.0, 0.0],
        }
        return [v_map[t] for t in texts]

    monkeypatch.setattr(ts, "embed_many", fake_embed_many)

    findings = await ts.TerminologyScanner().run(assets)
    drift = [f for f in findings if set(f.variants) >= {"AI-powered", "AI-assisted"}]
    assert len(drift) == 1, f"expected one drift cluster, got {[f.variants for f in findings]}"
    f = drift[0]
    assert f.occurrences["AI-powered"] == 3
    assert f.occurrences["AI-assisted"] == 2
    assert len(f.affected_asset_ids) == 5
