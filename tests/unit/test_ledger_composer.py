"""Ledger composer — pure template walk over plan + brief + drafts. No LLM."""
from __future__ import annotations

from uuid import uuid4

from agents import ledger_composer
from agents.ledger_composer import LedgerComposer, compose_ledger
from core.schemas import (
    AudienceDescription,
    Brief,
    CampaignIdentity,
    ChannelPlan,
    ChannelRef,
    ExecutionPlan,
    PlanTimeline,
    QACheckpoint,
    ResolvedObjective,
    TimelineWeek,
)
from core.state import CampaignState


def _state(monkeypatch) -> CampaignState:
    brief = Brief(
        campaign_name="Q3",
        business_objective="Convert 200 enterprise trials.",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="Stop reporting on yesterday.",
        channels=[ChannelRef(name="LinkedIn"), ChannelRef(name="Email")],
        raw_source="(brief)",
    )
    plan = ExecutionPlan(
        brief_id=brief.id,
        campaign_identity=CampaignIdentity(name="Q3 Push", brief_id=brief.id),
        audience_summary="enterprise VPs",
        resolved_objectives=[
            ResolvedObjective(
                objective="Convert 200 enterprise trials.",
                addressed_by_channels=["LinkedIn", "Email"],
            )
        ],
        channels=[
            ChannelPlan(
                channel_name="LinkedIn", spec_ref=uuid4(), owner_placeholder="[X]", cta="Book a demo"
            ),
            ChannelPlan(
                channel_name="Email", spec_ref=uuid4(), owner_placeholder="[Y]", cta="Book a demo"
            ),
        ],
        timeline=PlanTimeline(
            weeks=[TimelineWeek(week_number=1)], dependencies=["LinkedIn requires copy_draft"]
        ),
        qa_checkpoints=[QACheckpoint(name="Copy review", occurs_at_week=2, description="Editorial.")],
    )
    fake_drafts = {
        str(plan.channels[0].id): {"angle": "pain-led", "voice_score": 78, "body": "x"},
        str(plan.channels[1].id): {"angle": "outcome-led", "voice_score": 82, "body": "y"},
    }
    monkeypatch.setattr(ledger_composer, "load_copy_drafts", lambda *_a, **_k: fake_drafts)
    return CampaignState(brief=brief, plan=plan)


def test_compose_ledger_includes_all_categories(monkeypatch):
    state = _state(monkeypatch)
    ledger = compose_ledger(state)
    # Must have entries for each known category we walk.
    field_paths = [e.field_path for e in ledger.entries]
    assert "resolved_objectives" in field_paths
    assert any(fp.startswith("channels[") for fp in field_paths)
    assert any(fp.endswith(".copy_draft") for fp in field_paths)
    assert "timeline.dependencies" in field_paths
    assert "qa_checkpoints" in field_paths

    # Every entry has citation + basis populated.
    for e in ledger.entries:
        assert e.citation
        assert e.basis in {"user_input", "rule", "exemplar", "llm_inference"}
        assert 0.0 <= e.confidence <= 1.0


def test_user_listed_channels_are_marked_user_input(monkeypatch):
    state = _state(monkeypatch)
    ledger = compose_ledger(state)
    li_entry = next(e for e in ledger.entries if e.field_path == "channels[LinkedIn]")
    assert li_entry.basis == "user_input"
