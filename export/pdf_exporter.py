"""Render an ExecutionPlan as a styled PDF.

Built with reportlab Platypus — pure Python, no system dependencies. The
PDF mirrors the structure of the markdown export but with the brand
palette (indigo accent on near-white) so it reads as a polished plan
artifact rather than a debug dump.

Sections (top to bottom):
    Title bar        — campaign name + meta line (brief id, version, status)
    Audience         — single paragraph
    Objectives       — bullet list, metric range + addressed channels
    Channels         — per channel: heading, CTA / owner / assets, copy draft
    Timeline         — week-by-week milestones + per-channel activities
    Dependencies     — bullet list (if any)
    QA Checkpoints   — bullet list
    Success Metrics  — bullet list

Returns raw PDF bytes. Used by `api/routes/export.py` as the response body.
"""
from __future__ import annotations

import html as _html
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.schemas import ExecutionPlan


# ---------------------------------------------------------------------------
# Brand colors — mirror the Lumeo light palette so the PDF reads on-brand
# ---------------------------------------------------------------------------

_ACCENT = colors.HexColor("#4F46E5")        # indigo-600
_ACCENT_SOFT = colors.HexColor("#EEF2FF")   # near-indigo background tint
_TEXT_PRIMARY = colors.HexColor("#0F172A")  # slate-900
_TEXT_SECONDARY = colors.HexColor("#475569")  # slate-600
_TEXT_MUTED = colors.HexColor("#94A3B8")    # slate-400
_BORDER = colors.HexColor("#E2E6EF")
_CODE_BG = colors.HexColor("#F4F6FB")


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "lumeo_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=_TEXT_PRIMARY,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "meta": ParagraphStyle(
            "lumeo_meta",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=_TEXT_SECONDARY,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "lumeo_h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=_ACCENT,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "lumeo_h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=_TEXT_PRIMARY,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "lumeo_body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=_TEXT_PRIMARY,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "lumeo_bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=_TEXT_PRIMARY,
            leftIndent=14,
            bulletIndent=2,
            spaceAfter=2,
        ),
        "label": ParagraphStyle(
            "lumeo_label",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=_TEXT_MUTED,
            spaceAfter=2,
        ),
        "code": ParagraphStyle(
            "lumeo_code",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=8.5,
            leading=12,
            textColor=_TEXT_PRIMARY,
            leftIndent=8,
            rightIndent=8,
            backColor=_CODE_BG,
            borderPadding=(6, 8, 6, 8),
            spaceAfter=8,
        ),
    }


def _esc(text: object) -> str:
    """Escape user content for reportlab's mini-XML rendering. ``<para>`` etc.
    are XML-like, so any literal ``<``/``&`` would otherwise break parsing."""
    if text is None:
        return ""
    s = str(text)
    return _html.escape(s).replace("\n", "<br/>")


def _fmt_metric(target: float | None, baseline: float | None) -> str:
    if target is None and baseline is None:
        return "—"
    if target is None:
        return f"baseline {baseline}"
    if baseline is None:
        return f"target {target}"
    return f"baseline {baseline} → target {target}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_plan_pdf(
    plan: ExecutionPlan,
    *,
    copy_drafts: dict[str, dict] | None = None,
) -> bytes:
    """Render ``plan`` as PDF bytes. ``copy_drafts`` is a map of
    ``str(channel.id) → {"body": ..., "voice_score": ..., "angle": ...}`` —
    pulled from Redis by the API route, optional here so unit tests can pass
    a static dict."""
    drafts = copy_drafts or {}
    styles = _build_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=plan.campaign_identity.name,
        author="Lumeo Campaign Studio",
    )

    story: list = []
    ci = plan.campaign_identity

    # ---- Title bar -------------------------------------------------------
    story.append(Paragraph(_esc(ci.name), styles["title"]))
    meta_parts = [
        f"Brief id: <font color='#475569'>{_esc(ci.brief_id)}</font>",
        f"Plan version: <b>{ci.version}</b>",
        f"Status: <b>{_esc(plan.status)}</b>",
        f"Generated: {_esc(ci.generated_at.isoformat(timespec='minutes'))}",
    ]
    story.append(Paragraph(" &nbsp;·&nbsp; ".join(meta_parts), styles["meta"]))
    story.append(HRFlowable(width="100%", thickness=0.6, color=_BORDER, spaceBefore=2, spaceAfter=10))

    # ---- Audience --------------------------------------------------------
    story.append(Paragraph("Audience", styles["h1"]))
    story.append(Paragraph(_esc(plan.audience_summary or "(none)"), styles["body"]))

    # ---- Objectives ------------------------------------------------------
    if plan.resolved_objectives:
        story.append(Paragraph("Objectives", styles["h1"]))
        for obj in plan.resolved_objectives:
            metric = _fmt_metric(obj.target, obj.baseline)
            channels = ", ".join(obj.addressed_by_channels) or "—"
            line = (
                f"<b>{_esc(obj.objective)}</b> — "
                f"<i>{_esc(obj.target_metric or 'metric n/a')}</i> ({_esc(metric)}) · "
                f"channels: {_esc(channels)}"
            )
            story.append(Paragraph(line, styles["bullet"], bulletText="•"))

    # ---- Channels --------------------------------------------------------
    if plan.channels:
        story.append(Paragraph("Channels", styles["h1"]))
        for ch in plan.channels:
            block: list = []
            block.append(Paragraph(_esc(ch.channel_name), styles["h2"]))
            ch_meta_rows = [
                ("CTA", ch.cta or "—"),
                ("Owner", ch.owner_placeholder or "—"),
            ]
            if ch.budget_share is not None:
                ch_meta_rows.append(("Budget share", str(ch.budget_share)))
            if ch.notes:
                ch_meta_rows.append(("Notes", ch.notes))
            ch_table = Table(
                [
                    [Paragraph(f"<b>{_esc(k)}</b>", styles["label"]),
                     Paragraph(_esc(v), styles["body"])]
                    for k, v in ch_meta_rows
                ],
                colWidths=[1.1 * inch, 5.6 * inch],
                hAlign="LEFT",
            )
            ch_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.4, _BORDER),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            block.append(ch_table)

            if ch.asset_requirements:
                block.append(Spacer(1, 6))
                block.append(Paragraph("ASSET REQUIREMENTS", styles["label"]))
                for asset in ch.asset_requirements:
                    block.append(
                        Paragraph(_esc(asset), styles["bullet"], bulletText="•")
                    )

            draft = drafts.get(str(ch.id))
            if draft and draft.get("body"):
                vs = draft.get("voice_score")
                vs_str = (
                    f" · voice {vs:.0f}/100"
                    if isinstance(vs, (int, float))
                    else ""
                )
                angle = draft.get("angle") or ""
                angle_str = f" · angle: {angle}" if angle else ""
                block.append(Spacer(1, 6))
                block.append(
                    Paragraph(
                        f"COPY DRAFT{_esc(vs_str)}{_esc(angle_str)}",
                        styles["label"],
                    )
                )
                block.append(
                    Paragraph(_esc(draft["body"].strip()), styles["code"])
                )
            block.append(Spacer(1, 8))
            # KeepTogether keeps the channel header + table on the same page
            # so we don't end a page on a heading.
            story.append(KeepTogether(block))

    # ---- Timeline --------------------------------------------------------
    if plan.timeline.weeks:
        story.append(Paragraph("Timeline", styles["h1"]))
        for w in plan.timeline.weeks:
            milestone_str = " · ".join(w.milestones) if w.milestones else ""
            header = f"Week {w.week_number}"
            if w.starts_on:
                header += f" — {w.starts_on.isoformat()}"
            if milestone_str:
                header += f" — {milestone_str}"
            story.append(Paragraph(_esc(header), styles["h2"]))
            for ch_name, activities in (w.channel_activities or {}).items():
                if not activities:
                    continue
                story.append(
                    Paragraph(
                        f"<b>{_esc(ch_name)}:</b> {_esc('; '.join(activities))}",
                        styles["bullet"],
                        bulletText="•",
                    )
                )

        if plan.timeline.dependencies:
            story.append(Paragraph("Dependencies", styles["h2"]))
            for d in plan.timeline.dependencies:
                story.append(
                    Paragraph(_esc(d), styles["bullet"], bulletText="•")
                )

    # ---- QA Checkpoints --------------------------------------------------
    if plan.qa_checkpoints:
        story.append(Paragraph("QA Checkpoints", styles["h1"]))
        for q in plan.qa_checkpoints:
            wk = f" (week {q.occurs_at_week})" if q.occurs_at_week else ""
            story.append(
                Paragraph(
                    f"<b>{_esc(q.name)}</b>{_esc(wk)} — {_esc(q.description)}",
                    styles["bullet"],
                    bulletText="•",
                )
            )

    # ---- Success Metrics -------------------------------------------------
    if plan.success_metric_bindings:
        story.append(Paragraph("Success Metrics", styles["h1"]))
        for m in plan.success_metric_bindings:
            owner = (
                f" · owner: {m.owner_placeholder}" if m.owner_placeholder else ""
            )
            story.append(
                Paragraph(
                    f"<b>{_esc(m.metric_name)}</b> — "
                    f"{_esc(m.measurement_approach)}{_esc(owner)}",
                    styles["bullet"],
                    bulletText="•",
                )
            )

    # Avoid a blank page at the end if the document is short.
    if not story or isinstance(story[-1], PageBreak):
        story.append(Spacer(1, 1))

    doc.build(story)
    return buffer.getvalue()
