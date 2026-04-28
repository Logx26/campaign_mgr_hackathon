"""Revision loop — bounded at MAX_REVISIONS regardless of critic verdict."""
from __future__ import annotations

from uuid import uuid4

import pytest

from core.schemas import (
    AudienceDescription,
    Brief,
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    ValidationFinding,
    ValidationReport,
)
from core.state import CampaignState
from orchestrator import nodes


def _persistent_blocking_state() -> CampaignState:
    brief = Brief(
        campaign_name="Q3",
        business_objective="x",
        target_audience=AudienceDescription(raw_description="y"),
        key_message="z",
        raw_source="(brief)",
    )
    plan = ExecutionPlan(
        brief_id=brief.id,
        campaign_identity=CampaignIdentity(name="X", brief_id=brief.id),
        audience_summary="y",
        channels=[
            ChannelPlan(
                channel_name="LinkedIn", spec_ref=uuid4(), owner_placeholder="[X]", cta="Book a demo"
            )
        ],
    )
    return CampaignState(session_id=uuid4(), brief=brief, plan=plan)


@pytest.mark.asyncio
async def test_revision_loop_caps_at_max_revisions(monkeypatch):
    """Even if critic always finds blocking issues, the loop must terminate at MAX_REVISIONS."""

    async def fake_critic_node(state):
        return state.model_copy(
            update={
                "validation_report": ValidationReport(
                    brief_id=state.brief.id,
                    plan_id=state.plan.id,
                    alignment_score=20.0,
                    findings=[
                        ValidationFinding(
                            category="consistency",
                            severity="error",
                            brief_passage="x",
                            plan_section_ref="y",
                            description="d",
                            suggested_fix="f",
                        )
                    ],
                )
            }
        )

    async def fake_generate_plan(state):
        return state  # no-op; we just need to count loop entries

    async def fake_ledger(state):
        return state

    monkeypatch.setattr(nodes, "critic_node", fake_critic_node)
    monkeypatch.setattr(nodes, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(nodes, "ledger_node", fake_ledger)

    state = _persistent_blocking_state()
    out = await nodes.review_and_revise(state)
    assert out.revision_count == nodes.MAX_REVISIONS
    assert out.validation_report is not None  # final report still present


@pytest.mark.asyncio
async def test_no_revision_when_critic_clean(monkeypatch):
    async def fake_critic_node(state):
        return state.model_copy(
            update={
                "validation_report": ValidationReport(
                    brief_id=state.brief.id,
                    plan_id=state.plan.id,
                    alignment_score=92.0,
                    findings=[],
                )
            }
        )

    async def fake_generate_plan(state):
        raise AssertionError("re-plan should NOT be called when critic is clean")

    async def fake_ledger(state):
        return state

    monkeypatch.setattr(nodes, "critic_node", fake_critic_node)
    monkeypatch.setattr(nodes, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(nodes, "ledger_node", fake_ledger)

    state = _persistent_blocking_state()
    out = await nodes.review_and_revise(state)
    assert out.revision_count == 0
