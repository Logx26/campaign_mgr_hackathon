"""Render an ExecutionPlan as a styled PowerPoint deck.

Built with python-pptx — pure Python, no system dependencies. The deck
mirrors the structure of the markdown / PDF exports but with a slide-
oriented layout: title slide, audience + objectives, one slide per
channel (with copy draft preview), timeline, QA + success metrics.

Visual design follows the Lumeo brand palette (indigo accent on near-
white canvas, slate-900 text, mint positive accent). Every slide carries
a small brand strip at the top so the deck reads as a polished artifact
rather than the default python-pptx blank theme.

Returns raw .pptx bytes — used by `api/routes/export.py` as the response
body.
"""
from __future__ import annotations

from io import BytesIO

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from core.schemas import ExecutionPlan


# ---------------------------------------------------------------------------
# Brand palette (mirrors `ui/styles.py`)
# ---------------------------------------------------------------------------

_ACCENT = RGBColor(0x4F, 0x46, 0xE5)         # indigo-600
_ACCENT_2 = RGBColor(0x0E, 0xA5, 0xE9)        # sky-500
_ACCENT_SOFT = RGBColor(0xEE, 0xF2, 0xFF)    # near-indigo tint
_TEXT_PRIMARY = RGBColor(0x0F, 0x17, 0x2A)   # slate-900
_TEXT_SECONDARY = RGBColor(0x47, 0x55, 0x69) # slate-600
_TEXT_MUTED = RGBColor(0x94, 0xA3, 0xB8)     # slate-400
_BORDER = RGBColor(0xE2, 0xE6, 0xEF)
_BG_PANEL = RGBColor(0xFF, 0xFF, 0xFF)
_BG_ELEVATED = RGBColor(0xF6, 0xF7, 0xFB)
_CODE_BG = RGBColor(0xF4, 0xF6, 0xFB)
_SUCCESS = RGBColor(0x16, 0xA3, 0x4A)

# 16:9 widescreen — standard modern slide size in EMUs.
_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)


# ---------------------------------------------------------------------------
# Low-level shape helpers
# ---------------------------------------------------------------------------


def _add_filled_rect(
    slide,
    *,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    fill: RGBColor,
    line: RGBColor | None = None,
    shape=MSO_SHAPE.RECTANGLE,
):
    sh = slide.shapes.add_shape(shape, left, top, width, height)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    return sh


def _add_text(
    slide,
    text: str,
    *,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    font_size: int = 14,
    bold: bool = False,
    color: RGBColor = _TEXT_PRIMARY,
    align: int = PP_ALIGN.LEFT,
    anchor: int = MSO_ANCHOR.TOP,
    font_name: str = "Calibri",
):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text or ""
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _add_bullets(
    slide,
    items: list[str | tuple[str, str]],
    *,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    font_size: int = 13,
    color: RGBColor = _TEXT_PRIMARY,
    bullet_color: RGBColor = _ACCENT,
):
    """Render a vertical bullet list. Items can be plain strings, or
    `(label, text)` tuples — the label is rendered bold accent-color
    in front of the text."""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        # Bullet glyph as a colored run.
        bullet_run = p.add_run()
        bullet_run.text = "•  "
        bullet_run.font.name = "Calibri"
        bullet_run.font.size = Pt(font_size)
        bullet_run.font.bold = True
        bullet_run.font.color.rgb = bullet_color
        if isinstance(item, tuple):
            label, text = item
            label_run = p.add_run()
            label_run.text = f"{label}: "
            label_run.font.name = "Calibri"
            label_run.font.size = Pt(font_size)
            label_run.font.bold = True
            label_run.font.color.rgb = _ACCENT
            text_run = p.add_run()
            text_run.text = text
            text_run.font.name = "Calibri"
            text_run.font.size = Pt(font_size)
            text_run.font.color.rgb = color
        else:
            text_run = p.add_run()
            text_run.text = item
            text_run.font.name = "Calibri"
            text_run.font.size = Pt(font_size)
            text_run.font.color.rgb = color
    return box


def _add_brand_strip(slide, page_label: str | None = None):
    """Top-of-slide brand strip — 0.5" indigo bar with the Lumeo wordmark on
    the left and an optional page label on the right."""
    # Indigo bar.
    _add_filled_rect(
        slide,
        left=Emu(0),
        top=Emu(0),
        width=_SLIDE_W,
        height=Inches(0.42),
        fill=_ACCENT,
    )
    # Wordmark.
    _add_text(
        slide,
        "Lumeo  |  Campaign Studio",
        left=Inches(0.4),
        top=Emu(0),
        width=Inches(6),
        height=Inches(0.42),
        font_size=14,
        bold=True,
        color=_BG_PANEL,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    if page_label:
        _add_text(
            slide,
            page_label,
            left=Inches(7),
            top=Emu(0),
            width=Inches(6),
            height=Inches(0.42),
            font_size=11,
            color=_BG_PANEL,
            align=PP_ALIGN.RIGHT,
            anchor=MSO_ANCHOR.MIDDLE,
        )


def _add_footer(slide, plan_name: str, slide_index: int, total: int):
    _add_text(
        slide,
        f"{plan_name}  ·  Slide {slide_index} of {total}",
        left=Inches(0.4),
        top=Inches(7.05),
        width=Inches(12.5),
        height=Inches(0.3),
        font_size=9,
        color=_TEXT_MUTED,
        align=PP_ALIGN.LEFT,
    )


def _add_section_header(slide, text: str, top: Emu = Inches(0.7)):
    """Slate-900 section heading with a thin indigo accent line beneath."""
    _add_text(
        slide,
        text,
        left=Inches(0.5),
        top=top,
        width=Inches(12.3),
        height=Inches(0.45),
        font_size=22,
        bold=True,
        color=_TEXT_PRIMARY,
    )
    _add_filled_rect(
        slide,
        left=Inches(0.5),
        top=top + Inches(0.45),
        width=Inches(0.7),
        height=Inches(0.06),
        fill=_ACCENT,
    )


def _add_meta_card(
    slide,
    rows: list[tuple[str, str]],
    *,
    left: Emu,
    top: Emu,
    width: Emu,
    row_height: Emu = Inches(0.36),
):
    """Light card with a list of label/value rows, used for channel meta."""
    card_height = row_height * len(rows) + Inches(0.2)
    _add_filled_rect(
        slide,
        left=left,
        top=top,
        width=width,
        height=card_height,
        fill=_BG_ELEVATED,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    for i, (label, value) in enumerate(rows):
        row_top = top + Inches(0.10) + row_height * i
        _add_text(
            slide,
            label.upper(),
            left=left + Inches(0.18),
            top=row_top,
            width=Inches(1.6),
            height=row_height,
            font_size=10,
            bold=True,
            color=_TEXT_MUTED,
            anchor=MSO_ANCHOR.TOP,
        )
        _add_text(
            slide,
            str(value or "—"),
            left=left + Inches(1.85),
            top=row_top,
            width=width - Inches(2.1),
            height=row_height,
            font_size=12,
            color=_TEXT_PRIMARY,
            anchor=MSO_ANCHOR.TOP,
        )


def _fmt_metric(target: float | None, baseline: float | None) -> str:
    if target is None and baseline is None:
        return "—"
    if target is None:
        return f"baseline {baseline}"
    if baseline is None:
        return f"target {target}"
    return f"baseline {baseline} → target {target}"


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Slide builders
# ---------------------------------------------------------------------------


def _build_title_slide(prs, plan: ExecutionPlan, slide_count: int):
    blank = prs.slide_layouts[6]  # blank layout
    slide = prs.slides.add_slide(blank)

    # Full-bleed soft accent background tint.
    _add_filled_rect(
        slide,
        left=Emu(0), top=Emu(0),
        width=_SLIDE_W, height=_SLIDE_H,
        fill=_ACCENT_SOFT,
    )

    # Big indigo block — left third of the slide.
    _add_filled_rect(
        slide,
        left=Emu(0), top=Emu(0),
        width=Inches(4.4), height=_SLIDE_H,
        fill=_ACCENT,
    )

    # Small Lumeo wordmark inside the indigo block, top-left.
    _add_text(
        slide,
        "LUMEO",
        left=Inches(0.5),
        top=Inches(0.55),
        width=Inches(3.4),
        height=Inches(0.4),
        font_size=12,
        bold=True,
        color=_BG_PANEL,
    )
    _add_text(
        slide,
        "CAMPAIGN  STUDIO",
        left=Inches(0.5),
        top=Inches(0.95),
        width=Inches(3.4),
        height=Inches(0.4),
        font_size=10,
        color=_ACCENT_SOFT,
    )

    # Vertical "Plan deck" caption near the bottom of the indigo block.
    _add_text(
        slide,
        "EXECUTION PLAN",
        left=Inches(0.5),
        top=Inches(6.6),
        width=Inches(3.4),
        height=Inches(0.4),
        font_size=11,
        bold=True,
        color=_ACCENT_SOFT,
    )

    # Right side — campaign name + meta.
    ci = plan.campaign_identity
    _add_text(
        slide,
        ci.name,
        left=Inches(4.9),
        top=Inches(2.4),
        width=Inches(8.0),
        height=Inches(1.6),
        font_size=40,
        bold=True,
        color=_TEXT_PRIMARY,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_filled_rect(
        slide,
        left=Inches(4.9),
        top=Inches(4.0),
        width=Inches(0.9),
        height=Inches(0.06),
        fill=_ACCENT,
    )
    audience_short = _truncate(plan.audience_summary or "—", 220)
    _add_text(
        slide,
        audience_short,
        left=Inches(4.9),
        top=Inches(4.2),
        width=Inches(8.0),
        height=Inches(1.5),
        font_size=14,
        color=_TEXT_SECONDARY,
    )

    # Status pill + version + generated date along the bottom.
    pill = _add_filled_rect(
        slide,
        left=Inches(4.9),
        top=Inches(5.85),
        width=Inches(1.4),
        height=Inches(0.36),
        fill=_BG_PANEL,
        line=_ACCENT,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    pill.text_frame.margin_left = Emu(0)
    pill.text_frame.margin_right = Emu(0)
    p = pill.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = ""
    r = p.add_run()
    r.text = (plan.status or "draft").upper()
    r.font.size = Pt(11)
    r.font.bold = True
    r.font.color.rgb = _ACCENT
    r.font.name = "Calibri"

    _add_text(
        slide,
        f"Plan version {plan.version}  ·  Generated {ci.generated_at.strftime('%Y-%m-%d %H:%M')}",
        left=Inches(6.4),
        top=Inches(5.85),
        width=Inches(6.5),
        height=Inches(0.36),
        font_size=11,
        color=_TEXT_SECONDARY,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    # Brief id muted bottom corner.
    _add_text(
        slide,
        f"Brief id  ·  {ci.brief_id}",
        left=Inches(4.9),
        top=Inches(6.85),
        width=Inches(8.0),
        height=Inches(0.3),
        font_size=9,
        color=_TEXT_MUTED,
    )


def _build_overview_slide(prs, plan: ExecutionPlan, idx: int, total: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    _add_brand_strip(slide, page_label="Overview")

    _add_section_header(slide, "Audience & Objectives", top=Inches(0.75))

    # Audience block.
    _add_text(
        slide,
        "AUDIENCE",
        left=Inches(0.5),
        top=Inches(1.5),
        width=Inches(6),
        height=Inches(0.3),
        font_size=11,
        bold=True,
        color=_TEXT_MUTED,
    )
    _add_filled_rect(
        slide,
        left=Inches(0.5),
        top=Inches(1.85),
        width=Inches(5.9),
        height=Inches(4.6),
        fill=_BG_ELEVATED,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    _add_text(
        slide,
        plan.audience_summary or "—",
        left=Inches(0.75),
        top=Inches(2.05),
        width=Inches(5.4),
        height=Inches(4.2),
        font_size=13,
        color=_TEXT_PRIMARY,
    )

    # Objectives block.
    _add_text(
        slide,
        "OBJECTIVES",
        left=Inches(6.7),
        top=Inches(1.5),
        width=Inches(6),
        height=Inches(0.3),
        font_size=11,
        bold=True,
        color=_TEXT_MUTED,
    )
    _add_filled_rect(
        slide,
        left=Inches(6.7),
        top=Inches(1.85),
        width=Inches(6.1),
        height=Inches(4.6),
        fill=_BG_ELEVATED,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    if plan.resolved_objectives:
        items: list[str | tuple[str, str]] = []
        for obj in plan.resolved_objectives:
            metric = _fmt_metric(obj.target, obj.baseline)
            channels = ", ".join(obj.addressed_by_channels) or "—"
            label = obj.objective
            tail = f"{obj.target_metric or 'metric n/a'} ({metric})  ·  channels: {channels}"
            items.append((label, tail))
        _add_bullets(
            slide,
            items,
            left=Inches(6.95),
            top=Inches(2.05),
            width=Inches(5.6),
            height=Inches(4.2),
            font_size=12,
        )
    else:
        _add_text(
            slide,
            "No objectives recorded.",
            left=Inches(6.95),
            top=Inches(2.05),
            width=Inches(5.6),
            height=Inches(4.2),
            font_size=13,
            color=_TEXT_SECONDARY,
        )

    _add_footer(slide, plan.campaign_identity.name, idx, total)


def _build_channel_slide(prs, plan: ExecutionPlan, ch, draft, idx: int, total: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    _add_brand_strip(slide, page_label=f"Channel  ·  {ch.channel_name}")

    _add_section_header(slide, ch.channel_name, top=Inches(0.75))

    # Meta card on the left.
    meta_rows = [
        ("CTA", ch.cta or "—"),
        ("Owner", ch.owner_placeholder or "—"),
    ]
    if ch.budget_share is not None:
        meta_rows.append(("Budget share", str(ch.budget_share)))
    if ch.asset_requirements:
        meta_rows.append(("Asset count", str(len(ch.asset_requirements))))
    if draft:
        vs = draft.get("voice_score")
        if isinstance(vs, (int, float)):
            meta_rows.append(("Voice score", f"{vs:.0f} / 100"))
        angle = draft.get("angle") or ""
        if angle:
            meta_rows.append(("Angle", angle))
    _add_meta_card(
        slide,
        meta_rows,
        left=Inches(0.5),
        top=Inches(1.5),
        width=Inches(5.5),
    )

    if ch.notes:
        notes_top = Inches(1.5) + Inches(0.36) * len(meta_rows) + Inches(0.5)
        _add_text(
            slide,
            "NOTES",
            left=Inches(0.5),
            top=notes_top,
            width=Inches(5.5),
            height=Inches(0.3),
            font_size=10,
            bold=True,
            color=_TEXT_MUTED,
        )
        _add_text(
            slide,
            ch.notes,
            left=Inches(0.5),
            top=notes_top + Inches(0.32),
            width=Inches(5.5),
            height=Inches(1.5),
            font_size=12,
            color=_TEXT_SECONDARY,
        )

    # Copy draft preview on the right.
    _add_text(
        slide,
        "COPY PREVIEW",
        left=Inches(6.3),
        top=Inches(1.5),
        width=Inches(6.5),
        height=Inches(0.3),
        font_size=11,
        bold=True,
        color=_TEXT_MUTED,
    )
    _add_filled_rect(
        slide,
        left=Inches(6.3),
        top=Inches(1.85),
        width=Inches(6.5),
        height=Inches(4.85),
        fill=_BG_PANEL,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    body_text = ""
    if draft and draft.get("body"):
        body_text = _truncate(str(draft["body"]).strip(), 1100)
    _add_text(
        slide,
        body_text or "(no copy draft yet)",
        left=Inches(6.55),
        top=Inches(2.05),
        width=Inches(6.0),
        height=Inches(4.5),
        font_size=11,
        color=_TEXT_PRIMARY if body_text else _TEXT_MUTED,
        font_name="Consolas",
    )

    # Asset requirements bar at the bottom-left.
    if ch.asset_requirements:
        _add_text(
            slide,
            "ASSET REQUIREMENTS  ·  " + " · ".join(ch.asset_requirements[:6]),
            left=Inches(0.5),
            top=Inches(6.5),
            width=Inches(5.5),
            height=Inches(0.4),
            font_size=10,
            color=_TEXT_SECONDARY,
        )

    _add_footer(slide, plan.campaign_identity.name, idx, total)


def _build_timeline_slide(prs, plan: ExecutionPlan, idx: int, total: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    _add_brand_strip(slide, page_label="Timeline")

    _add_section_header(slide, "Timeline", top=Inches(0.75))

    weeks = plan.timeline.weeks
    if not weeks:
        _add_text(
            slide,
            "No timeline weeks recorded.",
            left=Inches(0.5),
            top=Inches(2),
            width=Inches(12.3),
            height=Inches(1),
            font_size=14,
            color=_TEXT_SECONDARY,
        )
        _add_footer(slide, plan.campaign_identity.name, idx, total)
        return

    items: list[str] = []
    for w in weeks:
        head = f"Week {w.week_number}"
        if w.starts_on:
            head += f" — {w.starts_on.isoformat()}"
        if w.milestones:
            head += "  ·  " + " · ".join(w.milestones)
        items.append(head)
        for ch_name, activities in (w.channel_activities or {}).items():
            if not activities:
                continue
            items.append(f"   {ch_name}: {'; '.join(activities)}")
    _add_bullets(
        slide,
        items,
        left=Inches(0.5),
        top=Inches(1.55),
        width=Inches(12.3),
        height=Inches(4.6),
        font_size=12,
    )

    if plan.timeline.dependencies:
        _add_text(
            slide,
            "DEPENDENCIES",
            left=Inches(0.5),
            top=Inches(6.25),
            width=Inches(12.3),
            height=Inches(0.3),
            font_size=10,
            bold=True,
            color=_TEXT_MUTED,
        )
        deps_text = "  ·  ".join(plan.timeline.dependencies[:4])
        _add_text(
            slide,
            _truncate(deps_text, 200),
            left=Inches(0.5),
            top=Inches(6.55),
            width=Inches(12.3),
            height=Inches(0.45),
            font_size=11,
            color=_TEXT_SECONDARY,
        )

    _add_footer(slide, plan.campaign_identity.name, idx, total)


def _build_qa_metrics_slide(prs, plan: ExecutionPlan, idx: int, total: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    _add_brand_strip(slide, page_label="QA & Success metrics")

    _add_section_header(slide, "QA & Success metrics", top=Inches(0.75))

    # QA checkpoints — left column.
    _add_text(
        slide,
        "QA CHECKPOINTS",
        left=Inches(0.5),
        top=Inches(1.5),
        width=Inches(6),
        height=Inches(0.3),
        font_size=11,
        bold=True,
        color=_TEXT_MUTED,
    )
    _add_filled_rect(
        slide,
        left=Inches(0.5),
        top=Inches(1.85),
        width=Inches(5.9),
        height=Inches(4.6),
        fill=_BG_ELEVATED,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    if plan.qa_checkpoints:
        items: list[str | tuple[str, str]] = []
        for q in plan.qa_checkpoints:
            wk = f" (week {q.occurs_at_week})" if q.occurs_at_week else ""
            items.append((q.name + wk, q.description))
        _add_bullets(
            slide,
            items,
            left=Inches(0.75),
            top=Inches(2.05),
            width=Inches(5.4),
            height=Inches(4.2),
            font_size=12,
        )
    else:
        _add_text(
            slide,
            "No QA checkpoints recorded.",
            left=Inches(0.75),
            top=Inches(2.05),
            width=Inches(5.4),
            height=Inches(4.2),
            font_size=13,
            color=_TEXT_SECONDARY,
        )

    # Success metrics — right column.
    _add_text(
        slide,
        "SUCCESS METRICS",
        left=Inches(6.7),
        top=Inches(1.5),
        width=Inches(6),
        height=Inches(0.3),
        font_size=11,
        bold=True,
        color=_TEXT_MUTED,
    )
    _add_filled_rect(
        slide,
        left=Inches(6.7),
        top=Inches(1.85),
        width=Inches(6.1),
        height=Inches(4.6),
        fill=_BG_ELEVATED,
        line=_BORDER,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE,
    )
    if plan.success_metric_bindings:
        sm_items: list[str | tuple[str, str]] = []
        for m in plan.success_metric_bindings:
            owner = f"  ·  owner: {m.owner_placeholder}" if m.owner_placeholder else ""
            sm_items.append((m.metric_name, m.measurement_approach + owner))
        _add_bullets(
            slide,
            sm_items,
            left=Inches(6.95),
            top=Inches(2.05),
            width=Inches(5.6),
            height=Inches(4.2),
            font_size=12,
        )
    else:
        _add_text(
            slide,
            "No success metrics recorded.",
            left=Inches(6.95),
            top=Inches(2.05),
            width=Inches(5.6),
            height=Inches(4.2),
            font_size=13,
            color=_TEXT_SECONDARY,
        )

    _add_footer(slide, plan.campaign_identity.name, idx, total)


def _build_closing_slide(prs, plan: ExecutionPlan, idx: int, total: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    _add_filled_rect(
        slide,
        left=Emu(0), top=Emu(0),
        width=_SLIDE_W, height=_SLIDE_H,
        fill=_ACCENT_SOFT,
    )
    _add_filled_rect(
        slide,
        left=Emu(0),
        top=Inches(7.0),
        width=_SLIDE_W,
        height=Inches(0.5),
        fill=_ACCENT,
    )
    _add_text(
        slide,
        "Ready to ship.",
        left=Inches(0.5),
        top=Inches(2.7),
        width=Inches(12.3),
        height=Inches(1.0),
        font_size=44,
        bold=True,
        color=_TEXT_PRIMARY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_text(
        slide,
        "Approved campaign plan generated by Lumeo Campaign Studio.",
        left=Inches(0.5),
        top=Inches(3.8),
        width=Inches(12.3),
        height=Inches(0.6),
        font_size=16,
        color=_TEXT_SECONDARY,
        align=PP_ALIGN.CENTER,
    )
    _add_text(
        slide,
        plan.campaign_identity.name,
        left=Inches(0.5),
        top=Inches(4.6),
        width=Inches(12.3),
        height=Inches(0.6),
        font_size=18,
        bold=True,
        color=_ACCENT,
        align=PP_ALIGN.CENTER,
    )
    _add_text(
        slide,
        f"LUMEO  |  CAMPAIGN STUDIO",
        left=Emu(0),
        top=Inches(7.0),
        width=_SLIDE_W,
        height=Inches(0.5),
        font_size=11,
        bold=True,
        color=_BG_PANEL,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_plan_pptx(
    plan: ExecutionPlan,
    *,
    copy_drafts: dict[str, dict] | None = None,
) -> bytes:
    """Render ``plan`` as PPTX bytes.

    ``copy_drafts`` maps ``str(channel.id) → {body, voice_score, angle}`` —
    same shape as `pdf_exporter` and `markdown_exporter`. Optional so unit
    tests can pass a static dict."""
    drafts = copy_drafts or {}
    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H

    # Compute total slide count up front so the footer "X of Y" reads right.
    total = (
        1                                       # title
        + 1                                     # overview
        + len(plan.channels)                    # one per channel
        + (1 if plan.timeline.weeks else 0)     # timeline
        + (
            1
            if (plan.qa_checkpoints or plan.success_metric_bindings)
            else 0
        )                                       # qa + metrics
        + 1                                     # closing
    )

    slide_idx = 0

    slide_idx += 1
    _build_title_slide(prs, plan, total)

    slide_idx += 1
    _build_overview_slide(prs, plan, slide_idx, total)

    for ch in plan.channels:
        slide_idx += 1
        draft = drafts.get(str(ch.id))
        _build_channel_slide(prs, plan, ch, draft, slide_idx, total)

    if plan.timeline.weeks:
        slide_idx += 1
        _build_timeline_slide(prs, plan, slide_idx, total)

    if plan.qa_checkpoints or plan.success_metric_bindings:
        slide_idx += 1
        _build_qa_metrics_slide(prs, plan, slide_idx, total)

    slide_idx += 1
    _build_closing_slide(prs, plan, slide_idx, total)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
