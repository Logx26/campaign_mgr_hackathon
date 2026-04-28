"""Execution plan — the headline output of W1."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel
from .channel import ChannelPlan


PlanStatus = Literal["draft", "in_review", "approved", "rejected"]


class CampaignIdentity(StrictModel):
    name: str
    brief_id: UUID
    version: int = 1
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ResolvedObjective(StrictModel):
    """Maps a brief objective to the plan elements that address it."""

    objective: str
    target_metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    addressed_by_channels: list[str] = Field(default_factory=list)


class TimelineWeek(StrictModel):
    week_number: int
    starts_on: date | None = None
    milestones: list[str] = Field(default_factory=list)
    channel_activities: dict[str, list[str]] = Field(default_factory=dict)


class PlanTimeline(StrictModel):
    weeks: list[TimelineWeek] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class QACheckpoint(StrictModel):
    name: str
    occurs_at_week: int | None = None
    description: str


class MetricBinding(StrictModel):
    metric_name: str
    measurement_approach: str
    owner_placeholder: str | None = None


class ExecutionPlan(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    brief_id: UUID
    version: int = 1
    campaign_identity: CampaignIdentity
    resolved_objectives: list[ResolvedObjective] = Field(default_factory=list)
    audience_summary: str  # short prose summary of resolved audience
    channels: list[ChannelPlan] = Field(default_factory=list)
    timeline: PlanTimeline = Field(default_factory=PlanTimeline)
    qa_checkpoints: list[QACheckpoint] = Field(default_factory=list)
    success_metric_bindings: list[MetricBinding] = Field(default_factory=list)
    assumptions: list[UUID] = Field(default_factory=list)  # refs to ledger entries
    risks: list[UUID] = Field(default_factory=list)  # refs to risk items (Tier 1)
    budget_findings: list[UUID] = Field(default_factory=list)  # refs (Tier 1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: PlanStatus = "draft"


# ---------------------------------------------------------------------------
# LLM-facing extraction shapes for plan generation (P5).
# ---------------------------------------------------------------------------


class ChannelPlanExtraction(StrictModel):
    """Skeleton produced by the Planner; enriched by ChannelSpecialist into a full ChannelPlan."""

    channel_name: str  # must match a seeded ChannelSpec.name
    owner_placeholder: str  # e.g. "[Demand Gen Lead]"
    cta: str  # one approved CTA — channel specialist may refine
    asset_requirements: list[str] = Field(default_factory=list)
    budget_share_pct: float | None = Field(default=None, ge=0.0, le=100.0)  # percent of total
    notes: str | None = None


class ChannelEnrichment(StrictModel):
    """Channel Specialist output — refines a skeleton ChannelPlanExtraction."""

    cta: str
    asset_requirements: list[str] = Field(default_factory=list)
    notes: str
    weekly_activities: list[str] = Field(
        default_factory=list,
        description="One activity per week the channel is active, in week order.",
    )


class CopyDraftExtraction(StrictModel):
    """LLM-side copy draft — server fills `id`, `channel_plan_ref`, `voice_score`, `variants`."""

    body: str
    angle: str  # benefit-led / pain-led / proof-led / outcome-led
    notes: str | None = None


class ResolvedObjectiveExtraction(StrictModel):
    objective: str
    target_metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    addressed_by_channels: list[str] = Field(default_factory=list)


class TimelineWeekExtraction(StrictModel):
    week_number: int = Field(ge=1)
    label: str = Field(default="", description="Short label, e.g. 'Kickoff', 'Launch', 'Wind-down'")
    milestones: list[str] = Field(default_factory=list)
    # channel_activities is filled by the timeline synthesizer using channel weekly_activities


class PlanSkeletonExtraction(StrictModel):
    """The Planner's primary output — a complete plan skeleton, sans copy and dependency-resolved timeline.

    Server fills `id`, `version`, `created_at`, `status`, `assumptions/risks/budget_findings` (refs).
    Channel Specialists enrich each `ChannelPlanExtraction` after this lands.
    """

    campaign_name: str
    audience_summary: str
    resolved_objectives: list[ResolvedObjectiveExtraction] = Field(default_factory=list)
    channels: list[ChannelPlanExtraction] = Field(default_factory=list)
    weeks: list[TimelineWeekExtraction] = Field(default_factory=list)
    qa_checkpoints: list[QACheckpoint] = Field(default_factory=list)
    success_metric_bindings: list[MetricBinding] = Field(default_factory=list)


class TimelineSynthesisExtraction(StrictModel):
    """Optional LLM-side timeline output when topological sort is ambiguous."""

    weeks: list[TimelineWeekExtraction] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
