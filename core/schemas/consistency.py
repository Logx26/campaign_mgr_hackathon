"""Multi-asset consistency report — Direction 3 output.

Tier 0 ships terminology + CTA findings + canonical suggestions.
Tone drift and audience-framing findings are Tier 1 (placeholders included for forward-compat).
"""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


class TerminologyFinding(StrictModel):
    cluster_id: str  # e.g. "cluster_0"
    variants: list[str]  # ["AI-powered", "AI-assisted"]
    canonical: str | None = None  # selected canonical (None = unresolved)
    occurrences: dict[str, int]  # variant -> count
    affected_asset_ids: list[UUID] = Field(default_factory=list)


class CTAFinding(StrictModel):
    asset_id: UUID
    raw_cta: str
    normalized_cta: str | None = None
    canonical_cta: str | None = None
    is_consistent: bool
    rule_id: str | None = None  # cta_patterns rule that matched (or None)


class ToneFinding(StrictModel):
    """Tier 1 placeholder."""

    asset_id: UUID
    voice_score: float
    deviation_from_mean: float
    flagged: bool


class AudienceFramingFinding(StrictModel):
    """Tier 1 placeholder."""

    asset_id: UUID
    declared_audience: str
    inferred_audience: str
    mismatch: bool
    rationale: str


class CanonicalSuggestion(StrictModel):
    cluster_id: str
    recommended_value: str
    rationale: str
    citation: str  # rule_id, term_dictionary entry, or section ref


class ConsistencyReport(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    asset_refs: list[UUID]
    terminology_findings: list[TerminologyFinding] = Field(default_factory=list)
    cta_findings: list[CTAFinding] = Field(default_factory=list)
    tone_findings: list[ToneFinding] = Field(default_factory=list)  # Tier 1
    audience_framing_findings: list[AudienceFramingFinding] = Field(default_factory=list)  # Tier 1
    canonical_suggestions: list[CanonicalSuggestion] = Field(default_factory=list)
    overall_consistency_index: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
