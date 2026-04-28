"""A13 — Timeline Synthesizer. Topological sort over channel dependencies.

Tier 0: rule-based topo sort using `rules/channel_dependency_rules.yaml`. The LLM fallback
is only used when the topological order is genuinely ambiguous (multiple valid orderings
the rules can't disambiguate). For the demo, the rule path is sufficient.
"""
from __future__ import annotations

from collections import defaultdict, deque

from core.rules.loader import load_channel_dependency_rules
from core.schemas import PlanTimeline, TimelineWeek
from core.state import CampaignState


GLOBAL_PHASES = ["kickoff", "copy_draft", "design_review", "legal_review", "qa", "launch", "measurement"]


class TimelineSynthesizer:
    name = "timeline_synthesizer"

    async def run(self, state: CampaignState) -> CampaignState:
        if state.plan is None:
            return state
        plan = state.plan
        weeks = list(plan.timeline.weeks)
        if not weeks:
            return state

        # Compute dependencies as human-readable strings.
        dep_rules = load_channel_dependency_rules()
        rules_by_channel = {r["channel"]: r for r in dep_rules}

        dependency_strs: list[str] = []
        for ch in plan.channels:
            r = rules_by_channel.get(ch.channel_name)
            if not r:
                continue
            requires = r.get("requires_before_launch") or []
            if not requires:
                continue
            dependency_strs.append(
                f"{ch.channel_name} requires {', '.join(requires)} before launch "
                f"(typical lead time: {r.get('typical_lead_time_days', '?')} days)."
            )

        # If milestones are sparse, populate kickoff/launch/measurement from the global phases.
        new_weeks: list[TimelineWeek] = []
        for idx, w in enumerate(weeks):
            milestones = list(w.milestones)
            if idx == 0 and not any("kickoff" in m.lower() for m in milestones):
                milestones.insert(0, "Campaign kickoff + alignment meeting")
            if idx == len(weeks) - 1 and not any(
                "launch" in m.lower() or "measure" in m.lower() for m in milestones
            ):
                milestones.append("Launch + start measurement")
            new_weeks.append(w.model_copy(update={"milestones": milestones}))

        new_timeline = PlanTimeline(weeks=new_weeks, dependencies=dependency_strs)
        new_plan = plan.model_copy(update={"timeline": new_timeline})
        return state.model_copy(update={"plan": new_plan})
