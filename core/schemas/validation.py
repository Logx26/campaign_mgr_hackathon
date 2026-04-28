"""Critic / validation report — Direction 2 output (also used inside W1 revision loop)."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


FindingCategory = Literal["coverage", "consistency", "feasibility", "compliance"]
FindingSeverity = Literal["info", "warning", "error", "blocker"]


class ValidationFinding(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    category: FindingCategory
    severity: FindingSeverity
    brief_passage: str  # quoted/excerpted passage from the brief
    plan_section_ref: str  # dotted path or section name in the plan
    description: str
    suggested_fix: str  # specific, actionable, not "review and revise"


class ValidationReport(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    brief_id: UUID
    plan_id: UUID
    alignment_score: float = Field(ge=0.0, le=100.0)
    findings: list[ValidationFinding] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# LLM-facing extraction shapes
# ---------------------------------------------------------------------------


class ValidationFindingExtraction(StrictModel):
    category: FindingCategory
    severity: FindingSeverity
    brief_passage: str
    plan_section_ref: str
    description: str
    suggested_fix: str


class ValidationReportExtraction(StrictModel):
    alignment_score: float = Field(ge=0.0, le=100.0)
    findings: list[ValidationFindingExtraction] = Field(default_factory=list)
