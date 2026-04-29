"""Eval metrics — gap-catch rate + plan completeness scoring."""
from __future__ import annotations

from uuid import uuid4

from core.schemas import (
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    Gap,
    GapList,
    QACheckpoint,
    ResolvedObjective,
    PlanTimeline,
    TimelineWeek,
)
from eval.metrics import assumption_citation_rate, gap_catch_rate, plan_completeness_score


def _gap(field_path: str, description: str) -> Gap:
    return Gap(
        field_path=field_path,
        description=description,
        severity="hard",
        source="rule",
    )


def test_gap_catch_rate_perfect_when_all_expected_caught():
    detected = GapList(
        brief_id=uuid4(),
        completeness_score=40.0,
        gaps=[
            _gap("budget.total", "missing budget"),
            _gap("timeline.launch_date", "no launch date"),
            _gap("success_metrics", "no quantified target"),
        ],
    )
    expected = {
        "hard_gaps": [
            {"field_path": "budget.total", "description": "Total budget not specified"},
            {"field_path": "timeline.launch_date", "description": "Launch date is ambiguous"},
        ],
        "soft_gaps": [
            {"field_path": "success_metrics", "description": "No quantified target on demos"},
        ],
    }
    assert gap_catch_rate(detected, expected) == 1.0


def test_gap_catch_rate_zero_when_no_detected_gaps_for_nonempty_expectations():
    expected = {"hard_gaps": [{"field_path": "budget.total", "description": "missing"}]}
    assert gap_catch_rate(None, expected) == 0.0
    assert gap_catch_rate(GapList(brief_id=uuid4(), completeness_score=100.0, gaps=[]), expected) == 0.0


def test_gap_catch_rate_one_when_no_expectations():
    """Vacuously perfect — there's nothing to miss."""
    detected = GapList(brief_id=uuid4(), completeness_score=80.0, gaps=[_gap("anything", "anywhere")])
    assert gap_catch_rate(detected, {}) == 1.0
    assert gap_catch_rate(detected, {"hard_gaps": [], "soft_gaps": []}) == 1.0


def test_gap_catch_rate_partial():
    detected = GapList(
        brief_id=uuid4(),
        completeness_score=60.0,
        gaps=[_gap("budget.total", "no budget given")],
    )
    expected = {
        "hard_gaps": [
            {"field_path": "budget.total", "description": "missing budget"},
            {"field_path": "timeline.launch_date", "description": "no launch date"},
        ]
    }
    # 1 out of 2 caught.
    assert gap_catch_rate(detected, expected) == 0.5


def test_plan_completeness_all_checks_pass():
    plan = ExecutionPlan(
        brief_id=uuid4(),
        campaign_identity=CampaignIdentity(name="Q3", brief_id=uuid4()),
        audience_summary="VPs of RevOps",
        resolved_objectives=[
            ResolvedObjective(objective="Drive demo requests from enterprise"),
        ],
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
                owner_placeholder="[Lifecycle]",
                cta="Book a demo",
            ),
        ],
        timeline=PlanTimeline(
            weeks=[
                TimelineWeek(week_number=1),
                TimelineWeek(week_number=2),
                TimelineWeek(week_number=3),
            ]
        ),
        qa_checkpoints=[QACheckpoint(name="Pre-launch", description="Review")],
    )
    expected = {
        "min_channels": 2,
        "min_weeks": 3,
        "required_objective_keywords": ["demo"],
        "required_channel_names": ["LinkedIn"],
        "requires_qa_checkpoint": True,
    }
    assert plan_completeness_score(plan, expected) == 1.0


def test_plan_completeness_partial_failure():
    plan = ExecutionPlan(
        brief_id=uuid4(),
        campaign_identity=CampaignIdentity(name="Q3", brief_id=uuid4()),
        audience_summary="VPs",
        channels=[
            ChannelPlan(channel_name="LinkedIn", spec_ref=uuid4(), owner_placeholder="x", cta="Book a demo")
        ],
        timeline=PlanTimeline(weeks=[TimelineWeek(week_number=1)]),
    )
    expected = {"min_channels": 2, "min_weeks": 3}  # both fail
    assert plan_completeness_score(plan, expected) == 0.0


def test_plan_completeness_returns_zero_for_none_plan():
    assert plan_completeness_score(None, {"min_channels": 1}) == 0.0


def test_assumption_citation_rate():
    class _E:
        def __init__(self, citation):
            self.citation = citation

    assert assumption_citation_rate([]) == 1.0
    assert assumption_citation_rate([_E("brand_book_§3.1"), _E("user_input")]) == 1.0
    assert assumption_citation_rate([_E(""), _E("ok"), _E(None)]) == pytest.approx(1 / 3)


import pytest  # noqa: E402  (used in last assertion)
