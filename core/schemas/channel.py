"""Channel specs (seeded, versioned) and per-channel plan slices."""
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


class ChannelSpec(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    name: str  # e.g. "LinkedIn", "Email", "Paid Search"
    version: int = 1
    max_length_words: int | None = None
    paragraph_style: str | None = None
    approved_cta_formats: list[str] = Field(default_factory=list)
    prohibited_cta_formats: list[str] = Field(default_factory=list)
    tone_guidelines: str | None = None
    content_conventions: list[str] = Field(default_factory=list)
    typical_budget_range_low: Decimal | None = None
    typical_budget_range_high: Decimal | None = None
    asset_types_required: list[str] = Field(default_factory=list)


class ChannelPlan(StrictModel):
    """One channel's slice of the ExecutionPlan."""

    id: UUID = Field(default_factory=uuid4)
    channel_name: str
    spec_ref: UUID  # ChannelSpec.id
    owner_placeholder: str  # e.g. "[Demand Gen Lead]"
    cta: str
    copy_draft_ref: UUID | None = None
    asset_requirements: list[str] = Field(default_factory=list)
    budget_share: Decimal | None = None
    notes: str | None = None
