"""A10 — Channel Specialist. One LLM call per channel, run in parallel via asyncio.gather."""
from __future__ import annotations

from dataclasses import dataclass

from core.llm.gateway import call_structured
from core.schemas import Brief, ChannelEnrichment, ChannelPlan
from core.state import CampaignState
from knowledge.channel_spec_library import get_channel_spec


@dataclass(frozen=True, slots=True)
class _SpecialistResult:
    channel_name: str
    enriched: ChannelEnrichment


class ChannelSpecialist:
    name = "channel_specialist"

    async def enrich_one(
        self,
        *,
        brief: Brief,
        channel: ChannelPlan,
        num_weeks: int,
        session_id,
    ) -> _SpecialistResult:
        spec = get_channel_spec(channel.channel_name) or {"name": channel.channel_name}
        draft = {
            "channel_name": channel.channel_name,
            "owner_placeholder": channel.owner_placeholder,
            "cta": channel.cta,
            "asset_requirements": channel.asset_requirements,
            "notes": channel.notes,
        }
        enriched = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": brief.model_dump(mode="json"),
                "channel_spec": spec,
                "channel_draft": draft,
                "num_weeks": num_weeks,
            },
            output_schema=ChannelEnrichment,
            session_id=session_id,
            agent_name=f"channel_specialist:{channel.channel_name}",
        )
        return _SpecialistResult(channel_name=channel.channel_name, enriched=enriched)


async def fan_out_channel_specialists(state: CampaignState) -> CampaignState:
    """Parallel fan-out across the plan's channels. Each specialist returns refined
    `cta / asset_requirements / notes / weekly_activities`. We then write `weekly_activities`
    into `plan.timeline.weeks[*].channel_activities[channel_name]` for the Gantt view.
    """
    import asyncio

    if state.plan is None or state.brief is None:
        return state
    plan = state.plan
    num_weeks = len(plan.timeline.weeks) or 6

    specialist = ChannelSpecialist()
    tasks = [
        specialist.enrich_one(
            brief=state.brief, channel=ch, num_weeks=num_weeks, session_id=state.session_id
        )
        for ch in plan.channels
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    by_name: dict[str, ChannelEnrichment] = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        by_name[r.channel_name] = r.enriched

    # Update channels in-place with enriched fields.
    new_channels: list[ChannelPlan] = []
    for ch in plan.channels:
        e = by_name.get(ch.channel_name)
        if e is None:
            new_channels.append(ch)
            continue
        new_channels.append(
            ch.model_copy(
                update={
                    "cta": e.cta,
                    "asset_requirements": e.asset_requirements,
                    "notes": e.notes,
                }
            )
        )

    # Update timeline with channel weekly activities.
    new_weeks = []
    for idx, week in enumerate(plan.timeline.weeks):
        activities: dict[str, list[str]] = dict(week.channel_activities)
        for channel_name, e in by_name.items():
            if idx < len(e.weekly_activities):
                activity = e.weekly_activities[idx]
                if activity and activity != "—":
                    activities[channel_name] = [activity]
        new_weeks.append(week.model_copy(update={"channel_activities": activities}))

    new_timeline = plan.timeline.model_copy(update={"weeks": new_weeks})
    new_plan = plan.model_copy(update={"channels": new_channels, "timeline": new_timeline})
    return state.model_copy(update={"plan": new_plan})
