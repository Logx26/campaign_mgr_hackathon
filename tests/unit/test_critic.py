"""Critic agent — mocked LLM gateway path. Validates extraction → ValidationReport promotion + merge."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents.critic import Critic, merge_findings
from core.schemas import (
    AudienceDescription,
    Brief,
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    ValidationFinding,
    ValidationFindingExtraction,
    ValidationReport,
    ValidationReportExtraction,
)
from core.state import CampaignState


def _state() -> CampaignState:
    brief = Brief(
        campaign_name="Q3",
        business_objective="Convert trials.",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="Stop reporting on yesterday.",
        raw_source="(brief)",
    )
    plan = ExecutionPlan(
        brief_id=brief.id,
        campaign_identity=CampaignIdentity(name="Q3 Push", brief_id=brief.id),
        audience_summary="enterprise VPs",
        channels=[
            ChannelPlan(
                channel_name="LinkedIn",
                spec_ref=uuid4(),
                owner_placeholder="[Demand Gen]",
                cta="Book a demo",
            )
        ],
    )
    return CampaignState(session_id=uuid4(), brief=brief, plan=plan)


@pytest.mark.asyncio
async def test_critic_promotes_extraction_to_validation_report(monkeypatch):
    fake = ValidationReportExtraction(
        alignment_score=72.0,
        findings=[
            ValidationFindingExtraction(
                category="consistency",
                severity="error",
                brief_passage="enterprise VPs",
                plan_section_ref="audience_summary",
                description="Audience summary uses generic 'enterprise VPs' without firmographic specificity.",
                suggested_fix="Add headcount range and industry to audience_summary.",
            )
        ],
    )

    async def fake_call(**kwargs):
        return fake

    import agents.critic as mod

    monkeypatch.setattr(mod, "call_structured", fake_call)
    monkeypatch.setattr(mod, "load_copy_drafts", lambda *_a, **_k: {})

    state = _state()
    out = await Critic().run(state)
    assert out.validation_report is not None
    assert out.validation_report.alignment_score == 72.0
    assert out.validation_report.brief_id == state.brief.id
    assert out.validation_report.plan_id == state.plan.id
    assert len(out.validation_report.findings) == 1
    assert out.validation_report.findings[0].severity == "error"


@pytest.mark.asyncio
async def test_critic_raises_when_brief_or_plan_missing():
    with pytest.raises(ValueError):
        await Critic().run(CampaignState())


def test_merge_findings_resorts_and_penalizes_alignment():
    base = ValidationReport(
        brief_id=uuid4(),
        plan_id=uuid4(),
        alignment_score=85.0,
        findings=[
            ValidationFinding(
                category="coverage",
                severity="info",
                brief_passage="x",
                plan_section_ref="y",
                description="d",
                suggested_fix="f",
            )
        ],
    )
    extra = [
        ValidationFinding(
            category="compliance",
            severity="blocker",
            brief_passage="a",
            plan_section_ref="b",
            description="prohibited term in copy",
            suggested_fix="remove",
        ),
        ValidationFinding(
            category="consistency",
            severity="warning",
            brief_passage="a",
            plan_section_ref="b",
            description="cta not in approved list",
            suggested_fix="swap",
        ),
    ]
    merged = merge_findings(base, extra)
    # Sorted: blocker, then info (info severity is rank 3 vs warning rank 2 → warning before info)
    severities = [f.severity for f in merged.findings]
    assert severities[0] == "blocker"
    assert "warning" in severities
    assert "info" in severities
    # Alignment penalized: 85 - 15 (blocker) - 3 (warning) = 67
    assert merged.alignment_score == 67.0
