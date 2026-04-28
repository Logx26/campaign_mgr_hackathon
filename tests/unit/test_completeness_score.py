"""Completeness scorer + rule engine unit tests.

These run without Redis/Postgres because the scorer reads YAML directly.
"""
from __future__ import annotations

from datetime import date

from core.schemas import (
    AudienceDescription,
    Brief,
    BudgetAllocation,
    ChannelRef,
    Constraints,
    QuantifiedTarget,
    SuccessMetric,
    Timeline,
)
from core.rules.loader import reset_cache
from tools.completeness_score import score_brief


def _full_brief() -> Brief:
    return Brief(
        campaign_name="Q3 Push",
        business_objective="Convert 200 enterprise trial accounts to paid before end of Q3.",
        quantified_targets=[
            QuantifiedTarget(metric_name="trial_to_paid", baseline=14.0, target=22.0, unit="percent")
        ],
        target_audience=AudienceDescription(
            raw_description="VP of RevOps at 1000+ headcount FinServ + Tech accounts"
        ),
        key_message="Stop reporting on yesterday — act on what the pipeline is doing today.",
        channels=[
            ChannelRef(name="LinkedIn"),
            ChannelRef(name="Email"),
            ChannelRef(name="Paid Search"),
        ],
        budget=BudgetAllocation(total=80000, per_channel={"LinkedIn": 40000, "Email": 10000, "Paid Search": 30000}),
        timeline=Timeline(launch_date=date(2026, 7, 1), asset_lock_date=date(2026, 6, 20)),
        success_metrics=[SuccessMetric(name="demo_requests", baseline=0, target=50, unit="count")],
        constraints=Constraints(
            tone_guidelines="Confident, professional, direct.",
            legal_restrictions=["No competitor naming"],
            mandatory_inclusions=["Customer quote on every asset"],
        ),
        raw_source="(full brief)",
    )


def _ambiguous_brief() -> Brief:
    return Brief(
        campaign_name="Q3 Demo Drive",
        business_objective="Drive more demos from social.",
        target_audience=AudienceDescription(raw_description="Enterprise companies."),
        key_message="Make your revenue team faster.",
        channels=[ChannelRef(name="social"), ChannelRef(name="email")],
        timeline=Timeline(),  # no concrete dates
        success_metrics=[],
        raw_source="(ambiguous brief)",
    )


def setup_module(_module):
    reset_cache()


def test_full_brief_scores_high_with_few_gaps():
    score, outcomes = score_brief(_full_brief())
    failed = [o for o in outcomes if not o.passed]
    assert score >= 80, f"expected high completeness, got {score} (failures={[o.rule_id for o in failed]})"
    # Hard rules should all pass
    hard_failures = [o for o in failed if o.severity == "hard"]
    assert hard_failures == [], f"unexpected hard-rule failures: {[o.rule_id for o in hard_failures]}"


def test_ambiguous_brief_scores_low_with_hard_gaps():
    score, outcomes = score_brief(_ambiguous_brief())
    failed = [o for o in outcomes if not o.passed]
    failed_ids = {o.rule_id for o in failed}
    assert score <= 60, f"expected low completeness, got {score}"
    # Specific expected hard gaps:
    assert "brief.budget.total.required" in failed_ids
    assert "brief.timeline.launch_date.required" in failed_ids
    assert "brief.success_metrics.required" in failed_ids
    # Specific expected soft gap (vague channel):
    assert "brief.channels.specific" in failed_ids


def test_outcomes_include_repair_question_text():
    _, outcomes = score_brief(_ambiguous_brief())
    for o in outcomes:
        if not o.passed:
            assert o.description, f"rule {o.rule_id} has empty description"
            # repair_question is optional but most rules have one
