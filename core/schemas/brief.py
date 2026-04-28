"""Canonical campaign brief schema.

The Brief is never mutated after creation. User clarifications land as `OverrideEntry` rows
in a separate table; agents read brief + overrides as the enriched view.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


SourceFormat = Literal["text", "markdown", "pdf", "docx", "transcript"]


class QuantifiedTarget(StrictModel):
    metric_name: str
    baseline: float | None = None
    target: float
    unit: str  # e.g. "percent", "count", "USD"


class AudienceSegmentRef(StrictModel):
    """Lightweight reference inside a Brief. Full AudienceSegment is a Tier 1 entity."""

    name: str
    notes: str | None = None


class AudienceDescription(StrictModel):
    raw_description: str
    resolved_segments: list[AudienceSegmentRef] = Field(default_factory=list)


class ChannelRef(StrictModel):
    name: str
    spec_id: UUID | None = None
    notes: str | None = None


class BudgetAllocation(StrictModel):
    total: Decimal | None = None
    per_channel: dict[str, Decimal] | None = None
    currency: str = "USD"


class Milestone(StrictModel):
    name: str
    target_date: date | None = None
    description: str | None = None


class Timeline(StrictModel):
    launch_date: date | None = None
    asset_lock_date: date | None = None
    milestones: list[Milestone] = Field(default_factory=list)


class SuccessMetric(StrictModel):
    name: str
    baseline: float | None = None
    target: float | None = None
    unit: str | None = None


class Constraints(StrictModel):
    mandatory_inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    tone_guidelines: str | None = None
    legal_restrictions: list[str] = Field(default_factory=list)


class OverrideEntry(StrictModel):
    """Captures one user clarification answer. Persisted separately from the Brief."""

    id: UUID = Field(default_factory=uuid4)
    field_path: str  # dotted path into Brief, e.g. "channels.0.name"
    old_value: str | None = None
    new_value: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Brief(StrictModel):
    """Canonical brief — what every downstream agent reads from."""

    id: UUID = Field(default_factory=uuid4)
    campaign_name: str
    business_objective: str
    quantified_targets: list[QuantifiedTarget] = Field(default_factory=list)
    target_audience: AudienceDescription
    key_message: str
    channels: list[ChannelRef] = Field(default_factory=list)
    budget: BudgetAllocation | None = None
    timeline: Timeline = Field(default_factory=Timeline)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    raw_source: str  # the original text the brief was parsed from
    source_format: SourceFormat = "text"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    overrides: list[OverrideEntry] = Field(default_factory=list)


class BriefExtraction(StrictModel):
    """LLM-facing extraction shape for Brief.

    Excludes server-generated fields (`id`, `created_at`, `overrides`) so the LLM is never
    asked to invent them. Azure strict-mode requires every property in `required` and the
    LLM emits `null` for fields it can't legitimately populate — which then fails Brief's
    UUID/datetime types. The agent constructs a real `Brief` from this extraction.
    """

    campaign_name: str
    business_objective: str
    quantified_targets: list[QuantifiedTarget] = Field(default_factory=list)
    target_audience: AudienceDescription
    key_message: str
    channels: list[ChannelRef] = Field(default_factory=list)
    budget: BudgetAllocation | None = None
    timeline: Timeline = Field(default_factory=Timeline)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    raw_source: str
    source_format: SourceFormat = "text"

    def to_brief(self) -> Brief:
        """Promote to a full Brief, filling server-generated fields locally."""
        return Brief.model_validate({**self.model_dump(), "overrides": []})
