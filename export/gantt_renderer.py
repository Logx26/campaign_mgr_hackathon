"""Render an ExecutionPlan's timeline as a single self-contained HTML Gantt chart.

No build step, no JS framework — inline CSS + a tiny vanilla JS for hover tooltips.
Designed to open standalone in any browser. Tested target: Chrome.

The bar layout uses CSS grid (one column per week, one row per channel + a top
"Milestones" row). Each bar is an absolutely-positioned div within the row.
"""
from __future__ import annotations

import html

from core.schemas import ExecutionPlan


_HEAD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: #1a1a1a; background: #fafafa; margin: 0; padding: 32px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px 0; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 24px; }}
  .gantt {{ background: #fff; border: 1px solid #e1e1e1; border-radius: 8px;
            padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow-x: auto; }}
  .gantt-grid {{ display: grid; grid-template-columns: 200px repeat({n_weeks}, 1fr); gap: 0; }}
  .week-header, .row-header, .cell {{ padding: 8px 6px; border-bottom: 1px solid #efefef; font-size: 0.85rem; }}
  .week-header {{ font-weight: 600; color: #333; text-align: center; background: #f7f7f7; }}
  .row-header {{ font-weight: 600; color: #333; background: #fafafa; border-right: 1px solid #efefef; }}
  .cell {{ position: relative; min-height: 38px; }}
  .activity {{ background: #2563eb; color: #fff; font-size: 0.75rem; line-height: 1.2;
               border-radius: 4px; padding: 4px 6px; margin: 2px 0; cursor: default; }}
  .activity.milestone {{ background: #f59e0b; color: #1a1a1a; font-weight: 600; }}
  .activity:hover {{ filter: brightness(1.1); }}
  .legend {{ font-size: 0.75rem; color: #666; margin-top: 12px; }}
  .legend span {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
                  vertical-align: middle; margin-right: 4px; }}
  .deps {{ margin-top: 16px; }}
  .deps h2 {{ font-size: 1rem; margin: 0 0 6px 0; }}
  .deps ul {{ margin: 0; padding-left: 18px; font-size: 0.85rem; color: #444; }}
</style>
</head><body>"""


def export_plan_gantt_html(plan: ExecutionPlan) -> str:
    weeks = sorted(plan.timeline.weeks, key=lambda w: w.week_number)
    if not weeks:
        return _HEAD.format(title=html.escape(plan.campaign_identity.name), n_weeks=1) + (
            f"<h1>{html.escape(plan.campaign_identity.name)}</h1>"
            "<p class='meta'>(no timeline weeks)</p></body></html>"
        )

    n_weeks = len(weeks)
    week_numbers = [w.week_number for w in weeks]
    channel_names: list[str] = []
    for ch in plan.channels:
        if ch.channel_name not in channel_names:
            channel_names.append(ch.channel_name)
    # Also pick up any channel referenced inside week.channel_activities that isn't on plan.channels.
    for w in weeks:
        for name in (w.channel_activities or {}):
            if name not in channel_names:
                channel_names.append(name)

    lines: list[str] = [_HEAD.format(title=html.escape(plan.campaign_identity.name), n_weeks=n_weeks)]
    lines.append(f"<h1>{html.escape(plan.campaign_identity.name)}</h1>")
    lines.append(
        f"<div class='meta'>Brief id: <code>{html.escape(str(plan.campaign_identity.brief_id))}</code> · "
        f"plan version: {plan.version} · status: <strong>{html.escape(plan.status)}</strong></div>"
    )
    lines.append("<div class='gantt'>")
    lines.append("<div class='gantt-grid'>")

    # Week header row
    lines.append("<div class='row-header'>&nbsp;</div>")
    for w in weeks:
        label = f"Week {w.week_number}"
        if w.starts_on:
            label += f"<br><span style='font-weight:400;color:#666'>{w.starts_on.isoformat()}</span>"
        lines.append(f"<div class='week-header'>{label}</div>")

    # Milestones row
    lines.append("<div class='row-header'>Milestones</div>")
    for w in weeks:
        cell_html = "<div class='cell'>"
        for m in (w.milestones or []):
            cell_html += f"<div class='activity milestone' title='{html.escape(m)}'>{html.escape(m)}</div>"
        cell_html += "</div>"
        lines.append(cell_html)

    # Channel rows
    for ch_name in channel_names:
        lines.append(f"<div class='row-header'>{html.escape(ch_name)}</div>")
        for w in weeks:
            cell_html = "<div class='cell'>"
            activities = (w.channel_activities or {}).get(ch_name) or []
            for a in activities:
                cell_html += f"<div class='activity' title='{html.escape(a)}'>{html.escape(a)}</div>"
            cell_html += "</div>"
            lines.append(cell_html)

    lines.append("</div>")  # gantt-grid
    lines.append(
        "<div class='legend'>"
        "<span style='background:#f59e0b'></span>milestone &nbsp;&nbsp;"
        "<span style='background:#2563eb'></span>channel activity"
        "</div>"
    )
    lines.append("</div>")  # gantt

    if plan.timeline.dependencies:
        lines.append("<div class='deps'><h2>Dependencies</h2><ul>")
        for d in plan.timeline.dependencies:
            lines.append(f"<li>{html.escape(d)}</li>")
        lines.append("</ul></div>")

    lines.append("</body></html>")
    return "\n".join(lines)
