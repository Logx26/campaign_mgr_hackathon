"""W3 multi-asset consistency — pre-stage the 5-asset Axion drift set, expect terminology
+ CTA drift detected and canonical recommendations citing the term dictionary.

Requires the live DB (term dictionary seeded) AND live Azure embeddings deployment. Skips
otherwise. The test does NOT require Azure chat — terminology + CTA + canonical resolution
are all deterministic when the dictionary path resolves the cluster.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from core.config import get_settings
from core.embeddings.client import is_embeddings_available, probe_embeddings_deployment
from orchestrator.nodes import consistency_scan

pytestmark = pytest.mark.integration


def _has_db() -> bool:
    return bool((get_settings().POSTGRES_DSN or "").strip())


def _load_sample_assets() -> list[dict]:
    out: list[dict] = []
    sample_dir = Path(__file__).resolve().parents[2] / "seeds" / "sample_assets"
    for path in sorted(sample_dir.glob("asset_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        body = (data.get("body") or "").strip()
        if body:
            out.append({"id": uuid4(), "body": body, "source_name": data.get("source_name")})
    return out


@pytest.mark.skipif(not _has_db(), reason="Postgres not configured")
@pytest.mark.skipif(not is_embeddings_available(), reason="Azure embeddings not configured")
@pytest.mark.asyncio
async def test_w3_consistency_scan_axion_demo_set():
    if not await probe_embeddings_deployment():
        pytest.skip("Azure embeddings deployment unreachable")

    assets = _load_sample_assets()
    assert len(assets) >= 5, f"expected ≥5 sample assets, got {len(assets)}"

    report = await consistency_scan(assets, session_id=uuid4())

    # Terminology: at least one cluster grouping AI-powered and AI-assisted variants.
    drift_cluster = next(
        (
            f for f in report.terminology_findings
            if {"AI-powered", "AI-assisted"}.issubset(set(f.variants))
        ),
        None,
    )
    assert drift_cluster is not None, (
        f"expected AI-powered + AI-assisted to cluster together; got: "
        f"{[f.variants for f in report.terminology_findings]}"
    )
    assert drift_cluster.occurrences.get("AI-powered", 0) == 3
    assert drift_cluster.occurrences.get("AI-assisted", 0) == 2

    # Canonical recommendation: "AI-assisted", citing the term dictionary entry.
    suggestion = next(
        (s for s in report.canonical_suggestions if s.cluster_id == drift_cluster.cluster_id),
        None,
    )
    assert suggestion is not None
    assert suggestion.recommended_value == "AI-assisted"
    assert "brand_book" in suggestion.citation.lower()

    # CTAs: 2 inconsistent (Schedule a call → Book a demo).
    inconsistent = [c for c in report.cta_findings if not c.is_consistent]
    assert len(inconsistent) >= 2
    assert all(c.canonical_cta == "Book a demo" for c in inconsistent if c.canonical_cta)

    # Overall index lands below 1.0 because of drift.
    assert 0.5 <= report.overall_consistency_index < 1.0
