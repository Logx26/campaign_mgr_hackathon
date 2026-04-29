"""Render an ExecutionPlan as a self-contained Markdown document.

The exporter walks the plan's structured fields and emits a hand-formatted Markdown string.
No Jinja template — keeps the dep surface small and lets us inline copy_drafts cleanly.
"""
from __future__ import annotations

from core.schemas import ExecutionPlan


def _fmt_metric(target: float | None, baseline: float | None) -> str:
    if target is None and baseline is None:
        return "—"
    if target is None:
        return f"baseline {baseline}"
    if baseline is None:
        return f"target {target}"
    return f"baseline {baseline} → target {target}"


def export_plan_markdown(plan: ExecutionPlan, *, copy_drafts: dict[str, dict] | None = None) -> str:
    drafts = copy_drafts or {}
    lines: list[str] = []
    ci = plan.campaign_identity

    lines.append(f"# {ci.name}")
    lines.append("")
    lines.append(f"_Brief id: `{ci.brief_id}` · plan version: `{plan.version}` · generated `{ci.generated_at.isoformat()}`_")
    lines.append("")
    lines.append(f"**Status:** `{plan.status}`")
    lines.append("")

    lines.append("## Audience")
    lines.append(plan.audience_summary or "_(none)_")
    lines.append("")

    if plan.resolved_objectives:
        lines.append("## Objectives")
        for obj in plan.resolved_objectives:
            metric = _fmt_metric(obj.target, obj.baseline)
            channels = ", ".join(obj.addressed_by_channels) or "—"
            lines.append(f"- **{obj.objective}** — _{obj.target_metric or 'metric n/a'}_ ({metric}) · channels: {channels}")
        lines.append("")

    if plan.channels:
        lines.append("## Channels")
        for ch in plan.channels:
            lines.append(f"### {ch.channel_name}")
            lines.append("")
            lines.append(f"- **CTA:** {ch.cta}")
            lines.append(f"- **Owner:** {ch.owner_placeholder}")
            if ch.budget_share is not None:
                lines.append(f"- **Budget share:** {ch.budget_share}")
            if ch.asset_requirements:
                lines.append("- **Assets:**")
                for asset in ch.asset_requirements:
                    lines.append(f"  - {asset}")
            if ch.notes:
                lines.append(f"- **Notes:** {ch.notes}")

            draft = drafts.get(str(ch.id))
            if draft and draft.get("body"):
                vs = draft.get("voice_score")
                vs_str = f" · voice {vs:.0f}/100" if isinstance(vs, (int, float)) else ""
                angle = draft.get("angle") or ""
                angle_str = f" · {angle}" if angle else ""
                lines.append("")
                lines.append(f"**Copy draft**{vs_str}{angle_str}")
                lines.append("")
                lines.append("```")
                lines.append(draft["body"].strip())
                lines.append("```")
            lines.append("")

    if plan.timeline.weeks:
        lines.append("## Timeline")
        for w in plan.timeline.weeks:
            milestone_str = " · ".join(w.milestones) if w.milestones else ""
            header = f"### Week {w.week_number}"
            if w.starts_on:
                header += f" — {w.starts_on.isoformat()}"
            if milestone_str:
                header += f" — {milestone_str}"
            lines.append(header)
            for ch_name, activities in (w.channel_activities or {}).items():
                if not activities:
                    continue
                lines.append(f"- **{ch_name}:** {'; '.join(activities)}")
            lines.append("")
        if plan.timeline.dependencies:
            lines.append("**Dependencies**")
            for dep in plan.timeline.dependencies:
                lines.append(f"- {dep}")
            lines.append("")

    if plan.qa_checkpoints:
        lines.append("## QA Checkpoints")
        for q in plan.qa_checkpoints:
            wk = f" (week {q.occurs_at_week})" if q.occurs_at_week else ""
            lines.append(f"- **{q.name}**{wk} — {q.description}")
        lines.append("")

    if plan.success_metric_bindings:
        lines.append("## Success Metrics")
        for m in plan.success_metric_bindings:
            owner = f" · owner: {m.owner_placeholder}" if m.owner_placeholder else ""
            lines.append(f"- **{m.metric_name}** — {m.measurement_approach}{owner}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
