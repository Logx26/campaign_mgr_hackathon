"""CampaignState — the typed payload that flows through every LangGraph node.

Stateless agents read and write to this object. The orchestrator graph owns it.
"""
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .schemas.base import StrictModel
from .schemas.brief import Brief
from .schemas.consistency import ConsistencyReport
from .schemas.gap import GapList
from .schemas.ledger import LedgerEntry
from .schemas.plan import ExecutionPlan
from .schemas.question import Question
from .schemas.trace import TraceEvent
from .schemas.validation import ValidationReport


EntryPoint = Literal[
    "plan_from_brief",
    "qa_existing_plan",
    "consistency_scan",
    "edit_plan",  # Tier 1 W4
    "query",  # Tier 2 W5
]


class CampaignState(StrictModel):
    """Shared state across the LangGraph orchestrator.

    Use Pydantic so we get type checks; LangGraph's Postgres saver can serialize Pydantic v2.
    """

    session_id: UUID = Field(default_factory=uuid4)
    entry_point: EntryPoint = "plan_from_brief"

    # Brief & gaps
    brief: Brief | None = None
    gaps: GapList | None = None
    questions: list[Question] = Field(default_factory=list)

    # Retrieval
    exemplars: list[UUID] = Field(default_factory=list)

    # Plan & validation
    plan: ExecutionPlan | None = None
    validation_report: ValidationReport | None = None

    # Consistency (W3)
    consistency_report: ConsistencyReport | None = None

    # Audit
    ledger: list[LedgerEntry] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)

    # Loop guards
    revision_count: int = 0
    clarification_round: int = 0

    # Approval
    human_approved: bool = False

    # Cost
    cost_usd: Decimal = Decimal("0")

    # Errors (non-fatal — fatal raises exceptions)
    error: str | None = None
