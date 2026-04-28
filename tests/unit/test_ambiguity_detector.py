"""Ambiguity Detector — mocked LLM gateway path; merges with rule-based gaps cleanly."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.ambiguity_detector import AmbiguityDetector
from core.schemas import (
    AudienceDescription,
    Brief,
    ChannelRef,
    Gap,
    GapExtraction,
    GapList,
    GapListExtraction,
)
from core.state import CampaignState


def _brief() -> Brief:
    return Brief(
        campaign_name="Q3 Demo Drive",
        business_objective="Drive more demos.",
        target_audience=AudienceDescription(raw_description="Enterprise companies."),
        key_message="Be faster.",
        channels=[ChannelRef(name="social"), ChannelRef(name="email")],
        raw_source="(brief)",
    )


@pytest.mark.asyncio
async def test_detector_merges_with_existing_hard_gaps_and_marks_soft(monkeypatch):
    brief = _brief()
    existing_hard = GapList(
        gaps=[
            Gap(
                field_path="budget.total",
                severity="hard",
                source="rule",
                rule_id="brief.budget.total.required",
                description="Total budget is not specified.",
            )
        ],
        brief_id=brief.id,
        completeness_score=42.0,
    )

    fake_llm_output = GapListExtraction(
        gaps=[
            GapExtraction(
                field_path="channels",
                severity="hard",  # LLM tries to claim hard — detector must coerce to soft
                source="rule",  # LLM tries to claim rule source — detector must coerce to llm
                rule_id="x",  # LLM tries to set a rule id — detector must null it
                description="'social' is ambiguous — which platforms?",
                suggested_questions=["Which platforms — LinkedIn, X, Instagram?"],
            )
        ],
    )

    async def fake_call_structured(**kwargs):
        assert kwargs["prompt_name"] == "ambiguity_detector"
        assert "brief_json" in kwargs["variables"]
        assert "existing_hard_gap_ids" in kwargs["variables"]
        return fake_llm_output

    import agents.ambiguity_detector as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    state = CampaignState(session_id=uuid4(), brief=brief, gaps=existing_hard)
    out = await AmbiguityDetector().run(state)

    assert out.gaps is not None
    # Original hard gap survives untouched
    hard = [g for g in out.gaps.gaps if g.severity == "hard"]
    assert len(hard) == 1
    assert hard[0].rule_id == "brief.budget.total.required"

    # LLM gap was coerced to soft + llm + rule_id None
    soft = [g for g in out.gaps.gaps if g.severity == "soft"]
    assert len(soft) == 1
    assert soft[0].source == "llm"
    assert soft[0].rule_id is None
    assert soft[0].field_path == "channels"

    # Completeness score preserved from rule pass
    assert out.gaps.completeness_score == 42.0


@pytest.mark.asyncio
async def test_detector_dedupes_overlap_with_rule_gaps(monkeypatch):
    brief = _brief()
    existing = GapList(
        gaps=[
            Gap(
                field_path="success_metrics",
                severity="hard",
                source="rule",
                rule_id="brief.success_metrics.required",
                description="Success metrics are missing.",
            )
        ],
        brief_id=brief.id,
        completeness_score=30.0,
    )

    fake_output = GapListExtraction(
        gaps=[
            GapExtraction(
                field_path="success_metrics",
                severity="soft",
                source="llm",
                description="Success metrics are missing.",  # exact same description
            )
        ],
    )

    async def fake_call_structured(**kwargs):
        return fake_output

    import agents.ambiguity_detector as mod

    monkeypatch.setattr(mod, "call_structured", fake_call_structured)

    state = CampaignState(brief=brief, gaps=existing)
    out = await AmbiguityDetector().run(state)
    # Dedupe: only the rule-based one survives
    matching = [g for g in out.gaps.gaps if g.field_path == "success_metrics"]
    assert len(matching) == 1
    assert matching[0].source == "rule"
