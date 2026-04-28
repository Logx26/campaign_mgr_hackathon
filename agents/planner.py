"""A09 — Planner. Brief + exemplars + channel specs → ExecutionPlan skeleton."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from core.llm.gateway import call_structured
from core.schemas import (
    CampaignIdentity,
    ChannelPlan,
    ExecutionPlan,
    PlanSkeletonExtraction,
    PlanTimeline,
    ResolvedObjective,
    TimelineWeek,
)
from core.state import CampaignState
from knowledge.channel_spec_library import list_channel_specs
from knowledge.exemplar_retriever import retrieve_exemplars


class Planner:
    name = "planner"

    async def run(self, state: CampaignState) -> CampaignState:
        if state.brief is None:
            raise ValueError("Planner requires state.brief to be set")

        channel_specs = list_channel_specs()
        exemplars = await retrieve_exemplars(state.brief, top_k=3)
        exemplar_payloads = [{"name": e.name, "body": e.body[:1500]} for e in exemplars]

        skeleton = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": state.brief.model_dump(mode="json"),
                "channel_specs": channel_specs,
                "exemplars": exemplar_payloads,
            },
            output_schema=PlanSkeletonExtraction,
            session_id=state.session_id,
            agent_name=self.name,
        )

        # Promote extraction → ExecutionPlan with server-managed fields filled in.
        spec_by_name = {s["name"]: s for s in channel_specs}
        channels: list[ChannelPlan] = []
        for ch_ext in skeleton.channels:
            spec = spec_by_name.get(ch_ext.channel_name)
            if spec is None:
                # Drop hallucinated channels; the prompt forbids them but be defensive.
                continue
            channels.append(
                ChannelPlan(
                    channel_name=ch_ext.channel_name,
                    spec_ref=uuid4(),  # ChannelSpec UUID is on the DB row; we lookup by name in app code
                    owner_placeholder=ch_ext.owner_placeholder,
                    cta=ch_ext.cta,
                    asset_requirements=ch_ext.asset_requirements,
                    budget_share=None,  # populated by budget allocator (Tier 1)
                    notes=ch_ext.notes,
                )
            )

        weeks = [
            TimelineWeek(
                week_number=w.week_number,
                milestones=w.milestones,
                channel_activities={},  # filled after channel specialists run
            )
            for w in sorted(skeleton.weeks, key=lambda w: w.week_number)
        ]

        plan = ExecutionPlan(
            brief_id=state.brief.id,
            campaign_identity=CampaignIdentity(
                name=skeleton.campaign_name,
                brief_id=state.brief.id,
                version=1,
                generated_at=datetime.utcnow(),
            ),
            resolved_objectives=[
                ResolvedObjective(
                    objective=o.objective,
                    target_metric=o.target_metric,
                    baseline=o.baseline,
                    target=o.target,
                    addressed_by_channels=o.addressed_by_channels,
                )
                for o in skeleton.resolved_objectives
            ],
            audience_summary=skeleton.audience_summary,
            channels=channels,
            timeline=PlanTimeline(weeks=weeks, dependencies=[]),
            qa_checkpoints=skeleton.qa_checkpoints,
            success_metric_bindings=skeleton.success_metric_bindings,
        )

        # Stash budget_share_pct hints in notes-side-channel via state attribute access — kept
        # transient since CampaignState forbids extras. The orchestrator reads from the channel
        # specialist agent for now; budget allocation lands fully in Tier 1.

        return state.model_copy(update={"plan": plan})
