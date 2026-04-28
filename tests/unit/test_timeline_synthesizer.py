"""Timeline synthesizer — adds kickoff + launch milestones and dependency strings."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.timeline_synthesizer import TimelineSynthesizer
from core.rules.loader import reset_cache
from core.schemas import (
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    PlanTimeline,
    TimelineWeek,
)
from core.state import CampaignState


def setup_module(_module):
    reset_cache()


def _state_with_plan() -> CampaignState:
    brief_id = uuid4()
    plan = ExecutionPlan(
        brief_id=brief_id,
        campaign_identity=CampaignIdentity(name="Test", brief_id=brief_id),
        audience_summary="enterprise VPs",
        channels=[
            ChannelPlan(
                channel_name="LinkedIn",
                spec_ref=uuid4(),
                owner_placeholder="[Demand Gen]",
                cta="Book a demo",
            ),
            ChannelPlan(
                channel_name="Email",
                spec_ref=uuid4(),
                owner_placeholder="[Mktg Ops]",
                cta="Book a demo",
            ),
        ],
        timeline=PlanTimeline(
            weeks=[
                TimelineWeek(week_number=1, milestones=[]),
                TimelineWeek(week_number=2, milestones=["Copy drafts done"]),
                TimelineWeek(week_number=3, milestones=[]),
            ]
        ),
    )
    return CampaignState(brief=None, plan=plan)


@pytest.mark.asyncio
async def test_kickoff_and_launch_milestones_inserted():
    state = _state_with_plan()
    out = await TimelineSynthesizer().run(state)
    weeks = out.plan.timeline.weeks
    assert any("kickoff" in m.lower() for m in weeks[0].milestones)
    assert any(("launch" in m.lower()) or ("measure" in m.lower()) for m in weeks[-1].milestones)


@pytest.mark.asyncio
async def test_dependencies_emitted_for_known_channels():
    state = _state_with_plan()
    out = await TimelineSynthesizer().run(state)
    deps = out.plan.timeline.dependencies
    assert any("LinkedIn" in d for d in deps)
    assert any("Email" in d for d in deps)
