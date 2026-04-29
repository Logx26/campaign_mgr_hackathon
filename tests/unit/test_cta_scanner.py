"""CTA scanner — regex catalog matching, prohibited-first ordering, LLM fallback path."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents import cta_scanner as cs
from core.schemas import CTAFindingExtraction


@pytest.fixture(autouse=True)
def _reset_pattern_cache():
    cs.reset_pattern_cache()
    yield
    cs.reset_pattern_cache()


@pytest.mark.asyncio
async def test_book_a_demo_canonical_match_is_consistent():
    aid = uuid4()
    findings = await cs.CTAScanner().run([{"id": aid, "body": "Book a demo today."}])
    assert len(findings) == 1
    f = findings[0]
    assert f.canonical_cta == "Book a demo"
    assert f.is_consistent is True
    assert f.rule_id == "cta_book_a_demo"


@pytest.mark.asyncio
async def test_schedule_a_call_normalizes_to_book_a_demo_inconsistent():
    """Synonym still recognized, but flagged as inconsistent because raw != canonical."""
    findings = await cs.CTAScanner().run([{"id": uuid4(), "body": "Schedule a call with our team."}])
    assert len(findings) == 1
    f = findings[0]
    assert f.canonical_cta == "Book a demo"
    assert f.is_consistent is False
    assert "schedule a call" in f.raw_cta.lower()


@pytest.mark.asyncio
async def test_prohibited_click_here_is_flagged_first():
    """`click here` must hit the prohibited rule even if other approved patterns are present."""
    findings = await cs.CTAScanner().run(
        [{"id": uuid4(), "body": "Click here to book a demo."}]
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "cta_prohibited_click_here"
    assert f.canonical_cta is None
    assert f.is_consistent is False


@pytest.mark.asyncio
async def test_no_match_no_session_returns_no_finding():
    """When regex misses and session_id is None, the LLM fallback is skipped silently."""
    findings = await cs.CTAScanner().run(
        [{"id": uuid4(), "body": "This is plain narrative copy with no call to action."}]
    )
    assert findings == []


@pytest.mark.asyncio
async def test_llm_fallback_runs_when_regex_misses(monkeypatch):
    fake_extraction = CTAFindingExtraction(
        raw_cta="Open to a 15-minute call?",
        normalized_cta="Open to a 15-minute call",
        is_cta=True,
    )

    async def fake_call(**_kwargs):
        return fake_extraction

    monkeypatch.setattr(cs, "call_structured", fake_call)

    findings = await cs.CTAScanner().run(
        [{"id": uuid4(), "body": "We'd love to chat. Open to a 15-minute call?"}],
        session_id=uuid4(),
    )
    # The body's "open to a 15-minute call" doesn't match any approved pattern, so the
    # LLM fallback is triggered.
    assert len(findings) == 1
    f = findings[0]
    assert f.is_consistent is False
    assert f.canonical_cta is None
    assert "15-minute" in f.raw_cta


@pytest.mark.asyncio
async def test_llm_fallback_returning_not_cta_emits_no_finding(monkeypatch):
    async def fake_call(**_kwargs):
        return CTAFindingExtraction(raw_cta="", normalized_cta=None, is_cta=False)

    monkeypatch.setattr(cs, "call_structured", fake_call)
    findings = await cs.CTAScanner().run(
        [{"id": uuid4(), "body": "Pure narrative copy."}], session_id=uuid4()
    )
    assert findings == []
