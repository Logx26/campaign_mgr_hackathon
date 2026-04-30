"""Per-channel copy drafts with brand voice scoring."""
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


class RuleViolation(StrictModel):
    rule_id: str
    rule_type: str  # e.g. "prohibited_term", "max_length", "tone"
    description: str
    severity: str  # e.g. "warning", "error"


class CopyDraft(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    channel_plan_ref: UUID
    body: str
    voice_score: float = Field(ge=0.0, le=100.0)
    voice_score_breakdown: dict[str, float] = Field(default_factory=dict)
    angle: str = "outcome-led"  # LLM-emitted or keyword-derived; never empty (UI never renders "?")
    rule_violations: list[RuleViolation] = Field(default_factory=list)
    variants: list[UUID] = Field(default_factory=list)  # refs to CopyVariant (Tier 1)


class CopyVariant(StrictModel):
    """Tier 1 — semantic-diversity variants."""

    id: UUID = Field(default_factory=uuid4)
    parent_draft_ref: UUID
    body: str
    diversity_score: float = Field(ge=0.0, le=1.0)
    angle: str  # e.g. "benefit-led", "pain-led", "proof-led"
