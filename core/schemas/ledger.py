"""Assumption ledger — auditable trail of every choice the system made without explicit user input."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


LedgerBasis = Literal["user_input", "rule", "exemplar", "llm_inference"]


class LedgerEntry(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    field_path: str  # which part of the plan this assumption affects
    assumption_text: str
    basis: LedgerBasis
    citation: str  # rule_id, exemplar_id, or brief passage
    confidence: float = Field(ge=0.0, le=1.0)
    created_by_agent: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AssumptionLedger(StrictModel):
    plan_id: UUID
    entries: list[LedgerEntry] = Field(default_factory=list)
    composed_at: datetime = Field(default_factory=datetime.utcnow)
