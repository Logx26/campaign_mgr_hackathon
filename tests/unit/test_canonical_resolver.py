"""Canonical resolver — dictionary-first resolution, LLM fallback when ambiguous."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents import canonical_resolver as cr
from core.schemas import CanonicalSuggestionExtraction, TerminologyFinding


def _finding(cluster_id: str, variants: list[str]) -> TerminologyFinding:
    return TerminologyFinding(
        cluster_id=cluster_id,
        variants=variants,
        occurrences={v: 1 for v in variants},
        affected_asset_ids=[uuid4()],
    )


@pytest.mark.asyncio
async def test_resolves_via_dictionary_when_canonical_present(monkeypatch):
    monkeypatch.setattr(
        cr,
        "_dictionary_lookup",
        lambda: [
            {
                "term": "AI-assisted",
                "type": "approved",
                "canonical": "AI-assisted",
                "synonyms": ["AI-powered", "AI-enabled"],
                "rule_ref": "brand_book_§3.1",
                "notes": "Use 'AI-assisted' to imply the human stays in control.",
            }
        ],
    )

    findings = [_finding("cluster_0", ["AI-powered", "AI-assisted"])]
    suggestions = await cr.CanonicalResolver().run(findings)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.recommended_value == "AI-assisted"
    assert s.citation == "brand_book_§3.1"
    assert "human stays in control" in s.rationale


@pytest.mark.asyncio
async def test_resolves_via_synonyms_only(monkeypatch):
    """Cluster contains only synonyms — canonical not visible — still resolves."""
    monkeypatch.setattr(
        cr,
        "_dictionary_lookup",
        lambda: [
            {
                "term": "book a demo",
                "type": "approved",
                "canonical": "book a demo",
                "synonyms": ["schedule a call", "request a demo"],
                "rule_ref": "brand_book_§5.1",
                "notes": "",
            }
        ],
    )
    findings = [_finding("cluster_0", ["schedule a call", "request a demo"])]
    suggestions = await cr.CanonicalResolver().run(findings)
    assert len(suggestions) == 1
    assert suggestions[0].recommended_value == "book a demo"
    assert suggestions[0].citation == "brand_book_§5.1"


@pytest.mark.asyncio
async def test_falls_back_to_llm_when_dictionary_silent(monkeypatch):
    monkeypatch.setattr(cr, "_dictionary_lookup", lambda: [])

    fake = CanonicalSuggestionExtraction(
        cluster_id="cluster_0",
        recommended_value="north star metric",
        rationale="More common variant in the asset set.",
        citation="llm_inference",
    )

    async def fake_call(**_kwargs):
        return fake

    monkeypatch.setattr(cr, "call_structured", fake_call)
    findings = [_finding("cluster_0", ["north star", "north star metric"])]
    suggestions = await cr.CanonicalResolver().run(findings, session_id=uuid4())
    assert len(suggestions) == 1
    assert suggestions[0].recommended_value == "north star metric"


@pytest.mark.asyncio
async def test_no_session_no_dictionary_returns_empty(monkeypatch):
    """Without dictionary AND without session, we cannot call LLM — silent skip."""
    monkeypatch.setattr(cr, "_dictionary_lookup", lambda: [])
    findings = [_finding("cluster_0", ["foo", "bar"])]
    suggestions = await cr.CanonicalResolver().run(findings, session_id=None)
    assert suggestions == []
