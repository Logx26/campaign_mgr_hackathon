"""Clarifier — mocked LLM gateway path."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.clarifier import Clarifier
from core.schemas import (
    AudienceDescription,
    Brief,
    Gap,
    GapList,
    QuestionExtraction,
    QuestionListExtraction,
)
from core.state import CampaignState


def _state_with_gaps() -> CampaignState:
    brief = Brief(
        campaign_name="Q3",
        business_objective="More demos.",
        target_audience=AudienceDescription(raw_description="Enterprise."),
        key_message="Be faster.",
        raw_source="(brief)",
    )
    gap = Gap(
        field_path="budget.total",
        severity="hard",
        source="rule",
        rule_id="brief.budget.total.required",
        description="Total budget missing.",
    )
    gap2 = Gap(
        field_path="channels",
        severity="soft",
        source="llm",
        description="'social' is ambiguous.",
    )
    gaps = GapList(gaps=[gap, gap2], brief_id=brief.id, completeness_score=42.0)
    return CampaignState(session_id=uuid4(), brief=brief, gaps=gaps), gap, gap2


@pytest.mark.asyncio
async def test_clarifier_returns_questions_capped_at_5(monkeypatch):
    state, gap1, gap2 = _state_with_gaps()

    fake = QuestionListExtraction(
        questions=[
            QuestionExtraction(
                prompt_text="What's the budget total?",
                type="free_text",
                suggested_default="$80,000",
                rationale="Required for channel sizing.",
                field_path="budget.total",
                gap_id=gap1.id,
            ),
            QuestionExtraction(
                prompt_text="Which platforms for 'social'?",
                type="multi_select",
                options=["LinkedIn", "X", "Instagram", "Facebook"],
                suggested_default="LinkedIn",
                rationale="'Social' resolves to specific platforms before planning.",
                field_path="channels",
                gap_id=gap2.id,
            ),
        ]
    )

    async def fake_call_structured(**kwargs):
        assert kwargs["prompt_name"] == "clarifier"
        return fake

    import agents.clarifier as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    out = await Clarifier().run(state)
    assert out.questions is not None
    assert 1 <= len(out.questions) <= 5
    assert {q.field_path for q in out.questions} == {"budget.total", "channels"}
    for q in out.questions:
        assert q.suggested_default
        assert q.rationale
        # Server-generated id present
        assert q.id is not None


@pytest.mark.asyncio
async def test_clarifier_drops_questions_with_unknown_gap_ids(monkeypatch):
    state, gap1, _ = _state_with_gaps()

    fake = QuestionListExtraction(
        questions=[
            QuestionExtraction(
                prompt_text="Real one.",
                type="free_text",
                suggested_default="x",
                rationale="r",
                field_path="budget.total",
                gap_id=gap1.id,
            ),
            QuestionExtraction(
                prompt_text="Hallucinated gap_id.",
                type="free_text",
                suggested_default="x",
                rationale="r",
                field_path="key_message",
                gap_id=uuid4(),  # not in state.gaps
            ),
        ]
    )

    async def fake_call_structured(**kwargs):
        return fake

    import agents.clarifier as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    out = await Clarifier().run(state)
    assert len(out.questions) == 1
    assert out.questions[0].field_path == "budget.total"


@pytest.mark.asyncio
async def test_clarifier_short_circuits_when_no_gaps():
    brief = Brief(
        campaign_name="Q3",
        business_objective="x.",
        target_audience=AudienceDescription(raw_description="y."),
        key_message="z.",
        raw_source="(brief)",
    )
    state = CampaignState(brief=brief, gaps=GapList(gaps=[], brief_id=brief.id, completeness_score=100.0))
    out = await Clarifier().run(state)
    assert out.questions == []
