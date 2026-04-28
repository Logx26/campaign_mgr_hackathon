"""Gap detection output: what the brief is missing or ambiguous about."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


GapSeverity = Literal["hard", "soft"]
GapSource = Literal["rule", "llm"]


class Gap(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    field_path: str  # dotted path into Brief, e.g. "budget.total"
    severity: GapSeverity
    source: GapSource
    rule_id: str | None = None  # populated when source='rule'
    description: str
    suggested_questions: list[str] = Field(default_factory=list)


class GapList(StrictModel):
    gaps: list[Gap]
    brief_id: UUID
    completeness_score: float = Field(ge=0.0, le=100.0)
    computed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# LLM-facing extraction shapes (no server-generated fields)
# ---------------------------------------------------------------------------


class GapExtraction(StrictModel):
    """LLM shape for one gap. Drops `id` (server-generated)."""

    field_path: str
    severity: GapSeverity
    source: GapSource
    rule_id: str | None = None
    description: str
    suggested_questions: list[str] = Field(default_factory=list)


class GapListExtraction(StrictModel):
    """LLM shape for a gap list. Drops `id`/`computed_at` from each gap and the list itself.

    The orchestrator promotes the extraction to full `Gap` + `GapList` rows server-side.
    """

    gaps: list[GapExtraction] = Field(default_factory=list)

    def to_gaps(self) -> list[Gap]:
        return [Gap(**g.model_dump()) for g in self.gaps]
