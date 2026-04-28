"""Brief Normalizer — mocked LLM gateway path."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.brief_normalizer import BriefNormalizer
from core.schemas import AudienceDescription, BriefExtraction
from core.state import CampaignState


@pytest.mark.asyncio
async def test_normalizer_returns_state_with_brief(monkeypatch):
    fake_extraction = BriefExtraction(
        campaign_name="Q3",
        business_objective="Convert trials.",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="Ship to market faster.",
        raw_source="(raw)",
    )

    async def fake_call_structured(**kwargs):
        assert kwargs["prompt_name"] == "brief_normalizer"
        assert "raw_text" in kwargs["variables"]
        return fake_extraction

    import agents.brief_normalizer as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    sid = uuid4()
    state = CampaignState(session_id=sid)
    out = await BriefNormalizer().run(state, raw_text="Q3 push", source_format="text")
    assert out.brief is not None
    assert out.brief.campaign_name == "Q3"
    # Server-generated fields populated locally
    assert out.brief.id is not None
    assert out.brief.created_at is not None
    # raw_source preserved from input even if LLM didn't echo it
    assert out.brief.raw_source == "(raw)" or out.brief.raw_source == "Q3 push"


@pytest.mark.asyncio
async def test_normalizer_preserves_raw_text_if_llm_blanks_it(monkeypatch):
    fake_extraction = BriefExtraction(
        campaign_name="Q3",
        business_objective="Convert trials.",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="Ship to market faster.",
        raw_source="",  # LLM dropped it
    )

    async def fake_call_structured(**kwargs):
        return fake_extraction

    import agents.brief_normalizer as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    out = await BriefNormalizer().run(CampaignState(), raw_text="real raw input", source_format="text")
    assert out.brief.raw_source == "real raw input"
