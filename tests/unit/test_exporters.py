"""Plan exporters — JSON / Markdown / Gantt HTML / PDF."""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID, uuid4

import pytest

from core.schemas import (
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    MetricBinding,
    PlanTimeline,
    QACheckpoint,
    ResolvedObjective,
    TimelineWeek,
)
from export import (
    export_plan_gantt_html,
    export_plan_json,
    export_plan_markdown,
    export_plan_pdf,
    export_plan_pptx,
)


@pytest.fixture
def fixture_plan() -> ExecutionPlan:
    brief_id = uuid4()
    return ExecutionPlan(
        brief_id=brief_id,
        campaign_identity=CampaignIdentity(name="Q3 Demo", brief_id=brief_id),
        audience_summary="Enterprise VPs of Revenue Operations.",
        resolved_objectives=[
            ResolvedObjective(
                objective="Drive trial-to-paid",
                target_metric="conversion_rate",
                baseline=14.0,
                target=22.0,
                addressed_by_channels=["Email", "LinkedIn"],
            )
        ],
        channels=[
            ChannelPlan(
                id=UUID("33333333-3333-4333-8333-333333333333"),
                channel_name="LinkedIn",
                spec_ref=uuid4(),
                owner_placeholder="[Demand Gen]",
                cta="Book a demo",
                asset_requirements=["post copy", "header image"],
                notes="Lead with stat.",
            ),
            ChannelPlan(
                id=UUID("44444444-4444-4444-8444-444444444444"),
                channel_name="Email",
                spec_ref=uuid4(),
                owner_placeholder="[Lifecycle]",
                cta="Book a demo",
                asset_requirements=["subject line", "body"],
            ),
        ],
        timeline=PlanTimeline(
            weeks=[
                TimelineWeek(
                    week_number=1,
                    starts_on=date(2026, 7, 1),
                    milestones=["Kickoff"],
                    channel_activities={"LinkedIn": ["Brief review"]},
                ),
                TimelineWeek(
                    week_number=2,
                    starts_on=date(2026, 7, 8),
                    milestones=["Launch"],
                    channel_activities={"Email": ["Send blast"], "LinkedIn": ["Publish post"]},
                ),
            ],
            dependencies=["Email body locked before LinkedIn promotion"],
        ),
        qa_checkpoints=[QACheckpoint(name="Pre-launch creative", occurs_at_week=1, description="Review copy")],
        success_metric_bindings=[
            MetricBinding(metric_name="conversion_rate", measurement_approach="weekly cohort")
        ],
    )


def test_json_exporter_round_trips(fixture_plan):
    body = export_plan_json(fixture_plan)
    parsed = json.loads(body)
    assert parsed["campaign_identity"]["name"] == "Q3 Demo"
    assert len(parsed["channels"]) == 2
    assert parsed["channels"][0]["cta"] == "Book a demo"


def test_json_exporter_includes_copy_drafts_when_supplied(fixture_plan):
    drafts = {"33333333-3333-4333-8333-333333333333": {"body": "Hook → proof → CTA", "voice_score": 78.0}}
    body = export_plan_json(fixture_plan, copy_drafts=drafts)
    parsed = json.loads(body)
    assert "copy_drafts" in parsed
    assert parsed["copy_drafts"]["33333333-3333-4333-8333-333333333333"]["voice_score"] == 78.0


def test_markdown_exporter_renders_all_top_level_sections(fixture_plan):
    md = export_plan_markdown(fixture_plan)
    assert "# Q3 Demo" in md
    assert "## Audience" in md
    assert "## Objectives" in md
    assert "## Channels" in md
    assert "### LinkedIn" in md
    assert "### Email" in md
    assert "## Timeline" in md
    assert "Week 1" in md and "Week 2" in md
    assert "## QA Checkpoints" in md
    assert "## Success Metrics" in md


def test_markdown_exporter_inlines_copy_drafts(fixture_plan):
    drafts = {
        "33333333-3333-4333-8333-333333333333": {
            "body": "Lead with the pain.",
            "voice_score": 85.0,
            "angle": "pain-led",
        }
    }
    md = export_plan_markdown(fixture_plan, copy_drafts=drafts)
    assert "Lead with the pain." in md
    assert "voice 85/100" in md
    assert "pain-led" in md


def test_gantt_exporter_emits_html_with_grid(fixture_plan):
    html = export_plan_gantt_html(fixture_plan)
    assert html.startswith("<!DOCTYPE html>")
    assert "Q3 Demo" in html
    assert 'class=\'gantt-grid\'' in html or 'class="gantt-grid"' in html
    # Two channels + 1 milestone row → 3 row-headers; week-header gets 1 (corner) + 2 weeks.
    assert html.count("row-header") >= 3
    assert "Kickoff" in html
    assert "Send blast" in html


def test_gantt_exporter_renders_dependencies(fixture_plan):
    html = export_plan_gantt_html(fixture_plan)
    assert "Dependencies" in html
    assert "Email body locked before LinkedIn promotion" in html


def test_gantt_exporter_handles_empty_timeline():
    plan = ExecutionPlan(
        brief_id=uuid4(),
        campaign_identity=CampaignIdentity(name="Empty", brief_id=uuid4()),
        audience_summary="—",
    )
    html = export_plan_gantt_html(plan)
    assert "no timeline weeks" in html


def test_pdf_exporter_emits_valid_pdf(fixture_plan):
    pdf_bytes = export_plan_pdf(fixture_plan)
    # %PDF-x.y magic number — every PDF starts with this prefix.
    assert pdf_bytes.startswith(b"%PDF-")
    # Plausible size — a populated plan should be at least a few KB.
    assert len(pdf_bytes) > 1500


def test_pdf_exporter_inlines_copy_drafts(fixture_plan):
    # The reportlab Story is opaque once flattened to PDF bytes, but we can
    # round-trip a sentinel through the exporter to confirm the body text
    # path is reached. A larger output when drafts are supplied is the
    # quickest way to assert the draft was actually written into the PDF.
    base = export_plan_pdf(fixture_plan)
    drafts = {
        "33333333-3333-4333-8333-333333333333": {
            "body": "Subject: Lead with the pain. " * 40,
            "voice_score": 85.0,
            "angle": "pain-led",
        }
    }
    with_draft = export_plan_pdf(fixture_plan, copy_drafts=drafts)
    assert with_draft.startswith(b"%PDF-")
    assert len(with_draft) > len(base)


def test_pdf_exporter_handles_minimal_plan():
    plan = ExecutionPlan(
        brief_id=uuid4(),
        campaign_identity=CampaignIdentity(name="Empty", brief_id=uuid4()),
        audience_summary="—",
    )
    pdf_bytes = export_plan_pdf(plan)
    assert pdf_bytes.startswith(b"%PDF-")


def test_pptx_exporter_emits_valid_pptx(fixture_plan):
    pptx_bytes = export_plan_pptx(fixture_plan)
    # PPTX is a ZIP container — magic bytes are PK\x03\x04.
    assert pptx_bytes[:2] == b"PK"
    # Plausible size — a populated plan with channels + timeline shouldn't
    # produce a tiny file.
    assert len(pptx_bytes) > 10_000


def test_pptx_exporter_includes_expected_slides(fixture_plan):
    """Inspect the generated PPTX to confirm slide count + titles. Uses
    python-pptx to round-trip the bytes back into a Presentation object."""
    from io import BytesIO

    from pptx import Presentation

    pptx_bytes = export_plan_pptx(fixture_plan)
    prs = Presentation(BytesIO(pptx_bytes))
    # Title + Overview + 2 channels + Timeline + QA/Metrics + Closing = 7.
    assert len(prs.slides) == 7

    # Concatenate every text frame in the deck so we can spot-check content.
    all_text: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        all_text.append(run.text)
    blob = "\n".join(all_text)
    assert "Q3 Demo" in blob              # campaign name on title + footer
    assert "LinkedIn" in blob             # channel slide
    assert "Email" in blob                # channel slide
    assert "Week 1" in blob or "Week 2" in blob  # timeline slide
    assert "Pre-launch creative" in blob  # QA checkpoint
    assert "Lumeo" in blob                # brand strip / closing


def test_pptx_exporter_handles_minimal_plan():
    plan = ExecutionPlan(
        brief_id=uuid4(),
        campaign_identity=CampaignIdentity(name="Empty", brief_id=uuid4()),
        audience_summary="—",
    )
    pptx_bytes = export_plan_pptx(plan)
    assert pptx_bytes[:2] == b"PK"


def test_pptx_exporter_inlines_copy_drafts(fixture_plan):
    """Confirm that supplied copy drafts land in the channel slides."""
    from io import BytesIO

    from pptx import Presentation

    sentinel = "SENTINEL_COPY_DRAFT_BODY_TEXT_FOR_VERIFICATION"
    drafts = {
        "33333333-3333-4333-8333-333333333333": {
            "body": sentinel,
            "voice_score": 78.0,
            "angle": "proof-led",
        }
    }
    pptx_bytes = export_plan_pptx(fixture_plan, copy_drafts=drafts)
    prs = Presentation(BytesIO(pptx_bytes))
    blob = "\n".join(
        run.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
        for para in shape.text_frame.paragraphs
        for run in para.runs
    )
    assert sentinel in blob
    assert "78" in blob               # voice score rendered as N/100
    assert "proof-led" in blob        # angle rendered
