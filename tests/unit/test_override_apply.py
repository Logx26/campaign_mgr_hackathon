"""Override application — user answers map back into the parsed Brief without mutating raw_source."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.schemas import AudienceDescription, Brief, ChannelRef, Timeline
from orchestrator.interrupts import apply_overrides_to_brief


def _base_brief() -> Brief:
    return Brief(
        campaign_name="Q3",
        business_objective="Drive more demos from social.",
        target_audience=AudienceDescription(raw_description="Enterprise companies."),
        key_message="Make your revenue team faster.",
        channels=[ChannelRef(name="social"), ChannelRef(name="email")],
        timeline=Timeline(),
        raw_source="(original brief)",
    )


def test_apply_budget_total():
    out = apply_overrides_to_brief(_base_brief(), {"budget.total": "80,000"})
    assert out.budget is not None
    assert out.budget.total == Decimal("80000")
    assert out.raw_source == "(original brief)"  # never mutated


def test_apply_per_channel_csv():
    out = apply_overrides_to_brief(
        _base_brief(),
        {"budget.per_channel": "LinkedIn:40000, Email:10000, Paid Search:30000"},
    )
    assert out.budget is not None
    assert out.budget.per_channel == {
        "LinkedIn": Decimal("40000"),
        "Email": Decimal("10000"),
        "Paid Search": Decimal("30000"),
    }


def test_apply_channels_replaces_vague_with_specific():
    out = apply_overrides_to_brief(_base_brief(), {"channels": "LinkedIn, Email, Paid Search"})
    names = [c.name for c in out.channels]
    assert names == ["LinkedIn", "Email", "Paid Search"]


def test_apply_launch_date():
    out = apply_overrides_to_brief(_base_brief(), {"timeline.launch_date": "2026-07-01"})
    assert out.timeline.launch_date == date(2026, 7, 1)


def test_apply_audience_description():
    out = apply_overrides_to_brief(
        _base_brief(),
        {"target_audience.raw_description": "VP RevOps at 1000+ FinServ accounts"},
    )
    assert "1000+" in out.target_audience.raw_description


def test_unknown_path_falls_back_to_constraint_note_without_crashing():
    # `nonexistent.path` is not handled — should land in mandatory_inclusions as audit, not raise.
    out = apply_overrides_to_brief(_base_brief(), {"foo.bar.baz": "weird value"})
    assert isinstance(out, Brief)


def test_quantified_targets_string_override_routes_to_mandatory_inclusions():
    """Regression for the override-500 bug. The Clarifier sometimes emits
    field_path=`quantified_targets` (a list[QuantifiedTarget] field) and the user's
    free-text answer cannot validly populate that. Must NOT raise."""
    brief = _base_brief()
    free_text = "Report both, but use existing trial accounts as the primary KPI"
    out = apply_overrides_to_brief(brief, {"quantified_targets": free_text})
    assert isinstance(out, Brief)
    # The answer is preserved as an audit line in mandatory_inclusions.
    assert any(
        "quantified_targets" in line and "primary KPI" in line
        for line in out.constraints.mandatory_inclusions
    ), out.constraints.mandatory_inclusions
    # quantified_targets stays valid (empty list).
    assert out.quantified_targets == []


def test_success_metrics_string_override_routes_to_mandatory_inclusions():
    """Same protection for the other list-typed top-level path the clarifier might emit."""
    brief = _base_brief()
    out = apply_overrides_to_brief(brief, {"success_metrics": "demo signups up 30%"})
    assert isinstance(out, Brief)
    assert any("success_metrics" in line for line in out.constraints.mandatory_inclusions)


def test_constraints_mandatory_inclusions_appends_not_overwrites():
    """A direct override on the bucket itself should append, preserving prior items."""
    brief = _base_brief()
    brief = brief.model_copy(
        update={
            "constraints": brief.constraints.model_copy(
                update={"mandatory_inclusions": ["already there"]}
            )
        }
    )
    out = apply_overrides_to_brief(
        brief, {"constraints.mandatory_inclusions": "Reference the customer story"}
    )
    assert "already there" in out.constraints.mandatory_inclusions
    assert "Reference the customer story" in out.constraints.mandatory_inclusions


def test_partial_failure_does_not_block_valid_overrides():
    """Mix one good override with one shape-incompatible override; the good one must apply."""
    brief = _base_brief()
    out = apply_overrides_to_brief(
        brief,
        {
            "budget.total": "180000",
            "quantified_targets": "Use trial-to-paid as primary KPI",
        },
    )
    # Good override applied
    assert out.budget is not None
    assert out.budget.total == Decimal("180000")
    # Incompatible override preserved as audit
    assert any("quantified_targets" in line for line in out.constraints.mandatory_inclusions)
