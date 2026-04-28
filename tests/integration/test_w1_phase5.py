"""End-to-end P5: Sample Brief A → full ExecutionPlan with 3 channels filled.

Requires Azure chat (and optionally embeddings — exemplar retrieval gracefully degrades).
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agents.brief_normalizer import BriefNormalizer
from agents.copy_drafter import load_copy_drafts
from core.config import get_settings
from core.state import CampaignState
from orchestrator.nodes import generate_plan

pytestmark = pytest.mark.integration


def _has_azure_chat() -> bool:
    s = get_settings()
    return bool(s.AZURE_OPENAI_API_KEY and s.AZURE_OPENAI_ENDPOINT and s.AZURE_OPENAI_DEPLOYMENT)


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_sample_brief_a_produces_complete_plan():
    brief_text = (
        Path(__file__).resolve().parents[2]
        / "seeds"
        / "exemplar_briefs"
        / "b2b_saas_q3_enterprise.md"
    ).read_text(encoding="utf-8")

    state = CampaignState(session_id=uuid4(), entry_point="plan_from_brief")
    state = await BriefNormalizer().run(state, raw_text=brief_text, source_format="markdown")
    assert state.brief is not None

    state = await generate_plan(state)
    plan = state.plan
    assert plan is not None
    assert len(plan.channels) >= 2, "expected at least 2 channels in the plan"
    # Every channel name must match a seeded ChannelSpec — planner promotes only known names.
    for ch in plan.channels:
        assert ch.channel_name in {
            "LinkedIn",
            "Email",
            "Paid Search",
            "Landing Page",
            "Event Page",
            "SDR Outreach",
        }
        assert ch.cta and ch.cta.strip()
    assert len(plan.timeline.weeks) >= 3
    # Timeline synthesizer always adds kickoff to week 1 if absent.
    assert any("kickoff" in m.lower() for m in plan.timeline.weeks[0].milestones)
    # Copy drafts cached under session+plan key.
    drafts = load_copy_drafts(state.session_id, plan.id)
    assert len(drafts) == len(plan.channels)
