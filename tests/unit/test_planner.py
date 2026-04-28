"""Planner — mocked LLM gateway path. Verifies extraction → ExecutionPlan promotion."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.planner import Planner
from core.schemas import (
    AudienceDescription,
    Brief,
    ChannelPlanExtraction,
    PlanSkeletonExtraction,
    QACheckpoint,
    ResolvedObjectiveExtraction,
    TimelineWeekExtraction,
)
from core.state import CampaignState


def _brief() -> Brief:
    return Brief(
        campaign_name="Q3 Push",
        business_objective="Convert 200 enterprise trials to paid by end of Q3.",
        target_audience=AudienceDescription(raw_description="VP RevOps at 1000+ headcount FinServ + Tech."),
        key_message="Stop reporting on yesterday — act on today's pipeline.",
        raw_source="(brief)",
    )


@pytest.fixture
def fake_skeleton():
    return PlanSkeletonExtraction(
        campaign_name="Q3 Enterprise Trial-to-Paid",
        audience_summary="VP RevOps at 1000+ headcount FinServ and Tech accounts in active trial.",
        resolved_objectives=[
            ResolvedObjectiveExtraction(
                objective="Convert enterprise trials to paid",
                target_metric="trial_to_paid_rate",
                baseline=14.0,
                target=22.0,
                addressed_by_channels=["LinkedIn", "Email", "Paid Search"],
            )
        ],
        channels=[
            ChannelPlanExtraction(
                channel_name="LinkedIn",
                owner_placeholder="[Demand Gen Lead]",
                cta="Book a demo",
                asset_requirements=["post copy", "header image (1200x627)"],
                budget_share_pct=40.0,
                notes="Lead with VP-RevOps pain point.",
            ),
            ChannelPlanExtraction(
                channel_name="Email",
                owner_placeholder="[Marketing Ops]",
                cta="Book a demo",
                asset_requirements=["subject line + preheader", "body copy (HTML + plain-text)"],
                budget_share_pct=20.0,
                notes="Segment by trial week 2 vs week 4.",
            ),
            ChannelPlanExtraction(
                channel_name="Paid Search",
                owner_placeholder="[Paid Media Manager]",
                cta="See pricing",
                asset_requirements=["3 RSAs with 8+ headlines", "5+ description variants"],
                budget_share_pct=40.0,
                notes="Bid on high-intent enterprise terms only.",
            ),
            # Hallucinated channel that's not in the seed catalog — should be dropped.
            ChannelPlanExtraction(
                channel_name="TikTok",
                owner_placeholder="[?]",
                cta="?",
            ),
        ],
        weeks=[
            TimelineWeekExtraction(week_number=1, label="Kickoff", milestones=["Brief alignment"]),
            TimelineWeekExtraction(week_number=2, label="Build", milestones=["Copy drafts complete"]),
            TimelineWeekExtraction(week_number=3, label="QA", milestones=["Legal sign-off"]),
            TimelineWeekExtraction(week_number=4, label="Launch", milestones=["Go live"]),
        ],
        qa_checkpoints=[
            QACheckpoint(name="Copy review", occurs_at_week=2, description="Editorial + brand voice review."),
            QACheckpoint(name="Legal review", occurs_at_week=3, description="Compliance sign-off before launch."),
        ],
        success_metric_bindings=[],
    )


@pytest.mark.asyncio
async def test_planner_produces_plan_and_drops_hallucinated_channels(monkeypatch, fake_skeleton):
    async def fake_call(**kwargs):
        return fake_skeleton

    async def fake_retrieve(brief, top_k=3):
        return []

    def fake_specs():
        return [
            {"name": "LinkedIn", "approved_cta_formats": ["Book a demo"]},
            {"name": "Email", "approved_cta_formats": ["Book a demo"]},
            {"name": "Paid Search", "approved_cta_formats": ["See pricing"]},
        ]

    import agents.planner as mod

    monkeypatch.setattr(mod, "call_structured", fake_call)
    monkeypatch.setattr(mod, "retrieve_exemplars", fake_retrieve)
    monkeypatch.setattr(mod, "list_channel_specs", fake_specs)

    state = CampaignState(session_id=uuid4(), brief=_brief())
    out = await Planner().run(state)

    assert out.plan is not None
    assert out.plan.brief_id == state.brief.id
    assert out.plan.campaign_identity.name == "Q3 Enterprise Trial-to-Paid"
    # TikTok dropped (not in seeded catalog)
    names = [c.channel_name for c in out.plan.channels]
    assert names == ["LinkedIn", "Email", "Paid Search"]
    assert len(out.plan.timeline.weeks) == 4
    assert out.plan.timeline.weeks[0].week_number == 1
    assert any("Convert enterprise trials" in r.objective for r in out.plan.resolved_objectives)


@pytest.mark.asyncio
async def test_planner_raises_when_no_brief():
    with pytest.raises(ValueError):
        await Planner().run(CampaignState())
