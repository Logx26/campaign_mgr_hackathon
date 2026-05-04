"""Smoke tests on the shared style + UI helpers — no Streamlit runtime required.

Where helpers call `st.markdown`, monkey-patch the streamlit module to capture the
emitted HTML so we can assert structural properties (e.g. kicker rendered ABOVE the H1
in `render_banner`, status pills emitted by `key_value_table`)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import ui.styles as ui_styles
from ui.components.brief_table import brief_to_rows, rows_as_table_input
from ui.styles import (
    PRODUCT_NAME,
    empty_state,
    key_value_table,
    render_banner,
    render_banner_with_legend,
    score_legend,
    scrub_override_prefix,
    section_header,
    severity_pill,
    step_rail,
    styled_error,
    top_header,
    traffic_color,
)


# ---------------------------------------------------------------------------
# Shared captured-markdown harness
# ---------------------------------------------------------------------------


class _CapturedMarkdown:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def markdown(self, html: str, **_kw) -> None:
        self.calls.append(html)

    def button(self, *_a, **_kw) -> bool:  # for empty_state
        return False


@pytest.fixture
def captured(monkeypatch):
    cap = _CapturedMarkdown()
    monkeypatch.setattr(ui_styles, "st", cap)
    return cap


# ---------------------------------------------------------------------------
# Severity pill (legacy contract — still required)
# ---------------------------------------------------------------------------


def test_severity_pill_emits_expected_classes():
    assert "pill-blocker" in severity_pill("blocker")
    assert "pill-error" in severity_pill("error")
    assert "pill-warning" in severity_pill("warning")
    assert "pill-info" in severity_pill("info")
    assert "pill-success" in severity_pill("success")
    assert "pill-neutral" in severity_pill("notarealseverity")


def test_severity_pill_accepts_custom_label():
    out = severity_pill("info", "ARMED")
    assert "ARMED" in out
    assert "pill-info" in out
    assert ">INFO<" not in out


def test_traffic_color_breaks_at_default_thresholds():
    assert traffic_color(85.0) == "var(--success)"
    assert traffic_color(70.0) == "var(--warning)"
    assert traffic_color(20.0) == "var(--danger)"
    assert traffic_color(0.92, hi=0.85, mid=0.6) == "var(--success)"
    assert traffic_color(0.7, hi=0.85, mid=0.6) == "var(--warning)"
    assert traffic_color(0.5, hi=0.85, mid=0.6) == "var(--danger)"


# ---------------------------------------------------------------------------
# Banner — kicker / tags MUST appear ABOVE the H1, never concatenated inline.
# Regression guard for: W1 liveW1 · Plan from Brief, P8 traceObservability, P8 regressionEval.
# ---------------------------------------------------------------------------


def test_render_banner_emits_clean_h1_no_tag_concatenation(captured):
    """Regression guard for the legacy `W1 liveW1 · Plan from Brief` headline bug —
    tags must NEVER appear inside the H1 element. Per the P11 Iter-2 follow-up the
    banner now ignores tags/kicker entirely; we still assert the H1 stays clean."""
    render_banner("Plan from Brief", "Subtitle here", tags=["W1", "live"])
    html = captured.calls[-1]
    h1_idx = html.find("<h1>")
    assert h1_idx != -1, "render_banner must emit an h1"
    h1_chunk = html[h1_idx : html.find("</h1>")]
    assert "Plan from Brief" in h1_chunk
    assert "liveW1" not in h1_chunk
    assert "<span class='axion-tag'" not in h1_chunk


def test_render_banner_kicker_argument_no_longer_rendered(captured):
    """`kicker` is accepted for backwards compatibility but is intentionally NOT
    rendered — the per-page banner now shows only title + subtitle."""
    render_banner("Plan QA", "subtitle", kicker="Workflow · Plan QA")
    html = captured.calls[-1]
    assert "Workflow · Plan QA" not in html
    assert "lumeo-overline" not in html


def test_render_banner_omits_overline_when_no_kicker_or_tags(captured):
    render_banner("Title only", "Subtitle")
    html = captured.calls[-1]
    assert "lumeo-overline" not in html


# ---------------------------------------------------------------------------
# Top header — centered product wordmark
# ---------------------------------------------------------------------------


def test_top_header_renders_global_dark_bar_with_wordmark(captured):
    """The top header is now a full-width fixed dark bar — `position: fixed` at the
    top of the viewport, spanning sidebar + main. Renders the product name + the
    canonical PRODUCT_TAGLINE next to it. The `subtitle` kwarg is accepted for
    backwards compatibility but ignored."""
    top_header()
    html = captured.calls[-1]
    assert "lumeo-global-header" in html
    assert "lumeo-global-header-inner" in html
    assert PRODUCT_NAME in html


def test_top_header_subtitle_argument_is_ignored(captured):
    """Per-page subtitle param is intentionally ignored; the canonical PRODUCT_TAGLINE
    is rendered uniformly across every page so the header stays consistent."""
    top_header(subtitle="QA mode")
    html = captured.calls[-1]
    assert "QA mode" not in html
    assert "lumeo-global-header" in html


# ---------------------------------------------------------------------------
# Section header
# ---------------------------------------------------------------------------


def test_section_header_emits_h2_without_kicker(captured):
    """`kicker` is accepted but not rendered — sections are titled plainly."""
    section_header("Review and approve", kicker="Step 5 · Review")
    html = captured.calls[-1]
    assert "<h2>" in html
    assert "Review and approve" in html
    assert "Step 5 · Review" not in html
    assert "lumeo-overline" not in html


def test_section_header_supports_action_text(captured):
    section_header("Findings", action="Top 3 by severity")
    html = captured.calls[-1]
    assert "lumeo-section-action" in html
    assert "Top 3 by severity" in html


# ---------------------------------------------------------------------------
# Step rail + score legend (new helpers)
# ---------------------------------------------------------------------------


def test_step_rail_renders_arrows_between_pills(captured):
    step_rail([("Brief", "done"), ("Analyze", "current"), ("Clarify", "pending")])
    html = captured.calls[-1]
    assert "lumeo-step-rail" in html
    # Arrow appears between consecutive pills (n-1 arrows for n steps).
    assert html.count("step-arrow") == 2
    # Each pill carries its state class.
    assert "step-pill done" in html
    assert "step-pill current" in html
    assert "step-pill pending" in html


def test_step_rail_unknown_state_falls_back_to_pending(captured):
    step_rail([("X", "weird-state")])
    html = captured.calls[-1]
    assert "step-pill pending" in html


def test_score_legend_renders_three_colored_chips(captured):
    score_legend()
    html = captured.calls[-1]
    assert "lumeo-legend-strip" in html
    # All three labels and color classes present.
    assert "Completeness" in html
    assert "Voice score" in html
    assert "Alignment" in html
    assert "legend-blue" in html
    assert "legend-mint" in html
    assert "legend-violet" in html


def test_render_banner_with_legend_emits_banner_then_legend_strip(captured):
    """The banner and the score legend are rendered as TWO sibling markdown calls
    so the legend strip can attach to the banner via CSS (border-radius continuation,
    no margin gap)."""
    render_banner_with_legend("Plan from Brief", "Subtitle line.")
    # Two markdown calls: the banner-with-legend wrapper, then the legend strip.
    assert len(captured.calls) >= 2
    banner_html = captured.calls[-2]
    legend_html = captured.calls[-1]
    assert "banner-with-legend" in banner_html
    assert "Plan from Brief" in banner_html
    assert "lumeo-legend-strip" in legend_html


# ---------------------------------------------------------------------------
# Key/value table — replaces all raw JSON dumps
# ---------------------------------------------------------------------------


def test_key_value_table_renders_status_pills_for_each_row(captured):
    rows = [
        ("Campaign name", "Q3 Drive", "confirmed"),
        ("Budget — total", "—", "missing"),
        ("Quantified targets", "—", "gap"),
    ]
    key_value_table(rows)
    html = captured.calls[-1]
    assert "lumeo-kv" in html
    assert "Campaign name" in html
    # Status pills get rendered inline via severity_pill().
    assert "pill-success" in html  # confirmed
    assert "pill-error" in html    # missing
    assert "pill-warning" in html  # gap


def test_key_value_table_two_column_mode(captured):
    rows = [("Field A", "Value A"), ("Field B", "Value B")]
    key_value_table(rows, columns=("Key", "Value", "Status"), status_col=False)
    html = captured.calls[-1]
    assert "Field A" in html and "Value B" in html
    assert "kv-status" not in html


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def test_empty_state_renders_icon_title_body(captured):
    empty_state("✅", "Brief is ready", "No hard or soft gaps remain.")
    html = captured.calls[-1]
    assert "lumeo-empty" in html
    assert "Brief is ready" in html
    assert "No hard or soft gaps remain." in html


# ---------------------------------------------------------------------------
# styled_error — never shows raw stack traces; details hidden in <details>
# ---------------------------------------------------------------------------


def test_styled_error_hides_details_in_collapsible(captured):
    styled_error("Network call failed.", details="HTTP 500\nstack...")
    html = captured.calls[-1]
    assert "lumeo-error" in html
    assert "<details>" in html
    assert "Network call failed." in html


def test_styled_error_without_details_omits_details_block(captured):
    styled_error("Simple message")
    html = captured.calls[-1]
    assert "lumeo-error" in html
    assert "<details>" not in html


# ---------------------------------------------------------------------------
# Override-prefix scrub — display only
# ---------------------------------------------------------------------------


def test_scrub_override_prefix_strips_audit_marker():
    inp = "[override:budget.total] Use existing program budgets only"
    assert scrub_override_prefix(inp) == "Use existing program budgets only"


def test_scrub_override_prefix_no_op_when_absent():
    assert scrub_override_prefix("Plain mandatory inclusion") == "Plain mandatory inclusion"


def test_scrub_override_prefix_handles_path_with_brackets_or_dots():
    inp = "[override:quantified_targets.0] Report both KPIs"
    assert scrub_override_prefix(inp) == "Report both KPIs"


def test_scrub_override_prefix_only_strips_first_occurrence():
    """Audit prefixes only ever appear at line start. Mid-string `[override:x]` is not
    intended as a marker and should NOT be stripped."""
    inp = "Mention that [override:budget.total] is a label"
    assert scrub_override_prefix(inp) == inp


# ---------------------------------------------------------------------------
# brief_to_rows — Brief → BriefRow with gap-aware status
# ---------------------------------------------------------------------------


def _minimal_brief(overrides=None):
    base = {
        "campaign_name": "Q3 Demo Drive",
        "business_objective": "grow self-serve trial signups",
        "key_message": "Faster, safer, smarter onboarding.",
        "target_audience": {"raw_description": "B2B SaaS demand-gen teams"},
        "channels": [{"name": "LinkedIn"}, {"name": "Email"}],
        "budget": {"total": 50000, "currency": "USD"},
        "timeline": {"launch_date": "2026-07-01"},
        "quantified_targets": [],
        "success_metrics": [],
        "constraints": {
            "mandatory_inclusions": ["[override:quantified_targets] Report both KPIs"],
            "exclusions": [],
            "legal_restrictions": [],
            "tone_guidelines": "professional, outcome-led",
        },
        "source_format": "markdown",
    }
    if overrides:
        base.update(overrides)
    return base


def test_brief_to_rows_marks_completed_fields_confirmed():
    rows = brief_to_rows(_minimal_brief())
    by_field = {r.field: r for r in rows}
    assert by_field["Campaign name"].status == "confirmed"
    assert by_field["Business objective"].status == "confirmed"
    assert by_field["Channels"].status == "confirmed"
    assert by_field["Budget — total"].status == "confirmed"


def test_brief_to_rows_flags_vague_channel_names_as_gap():
    rows = brief_to_rows(
        _minimal_brief({"channels": [{"name": "social"}, {"name": "performance"}]})
    )
    by_field = {r.field: r for r in rows}
    assert by_field["Channels"].status == "gap"


def test_brief_to_rows_marks_missing_budget_total_missing():
    rows = brief_to_rows(_minimal_brief({"budget": None}))
    by_field = {r.field: r for r in rows}
    assert by_field["Budget — total"].status == "missing"


def test_brief_to_rows_uses_gaplist_to_override_audience_status():
    """If audience text is non-empty but a soft gap fired against it, we must surface it."""
    gaps = {
        "gaps": [
            {
                "field_path": "target_audience.raw_description",
                "severity": "soft",
                "description": "Audience description lacks firmographics.",
                "source": "rule",
            }
        ]
    }
    rows = brief_to_rows(_minimal_brief(), gaps=gaps)
    by_field = {r.field: r for r in rows}
    assert by_field["Target audience"].status == "gap"


def test_brief_to_rows_scrubs_override_prefix_in_mandatory_inclusions():
    rows = brief_to_rows(_minimal_brief())
    inclusion_row = next(r for r in rows if r.field.startswith("Mandatory inclusion"))
    # Render-time scrub: the audit prefix must NOT appear on screen.
    assert "[override:" not in inclusion_row.value
    assert "Report both KPIs" in inclusion_row.value


def test_rows_as_table_input_returns_field_value_status_tuples():
    rows = brief_to_rows(_minimal_brief())
    tuples = list(rows_as_table_input(rows))
    assert all(len(t) == 3 for t in tuples)
    assert any(t[0] == "Campaign name" and t[1] == "Q3 Demo Drive" for t in tuples)
