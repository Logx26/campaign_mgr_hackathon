"""Completeness Checker agent — wraps the scorer and emits a GapList in CampaignState."""
from __future__ import annotations

import pytest

from agents.completeness_checker import CompletenessChecker
from core.rules.loader import reset_cache
from core.schemas import AudienceDescription, Brief, ChannelRef, Timeline
from core.state import CampaignState


def setup_module(_module):
    reset_cache()


@pytest.mark.asyncio
async def test_checker_produces_gap_list_with_score():
    brief = Brief(
        campaign_name="Q3 Demo Drive",
        business_objective="Drive more demos from social.",
        target_audience=AudienceDescription(raw_description="Enterprise companies."),
        key_message="Make your revenue team faster.",
        channels=[ChannelRef(name="social"), ChannelRef(name="email")],
        timeline=Timeline(),
        success_metrics=[],
        raw_source="(brief)",
    )
    state = CampaignState(brief=brief)
    checker = CompletenessChecker()
    out = await checker.run(state)
    assert out.gaps is not None
    assert out.gaps.brief_id == brief.id
    assert 0 <= out.gaps.completeness_score <= 100
    assert any(g.severity == "hard" for g in out.gaps.gaps)
    # Every rule-emitted gap must carry a rule_id and source='rule'
    for g in out.gaps.gaps:
        assert g.source == "rule"
        assert g.rule_id is not None


@pytest.mark.asyncio
async def test_checker_raises_when_no_brief():
    checker = CompletenessChecker()
    with pytest.raises(ValueError):
        await checker.run(CampaignState())
