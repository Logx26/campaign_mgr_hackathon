"""Plan generation + retrieval + review (P5 + P6) endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm.attributes import flag_modified

from agents.copy_drafter import load_copy_drafts
from agents.ledger_composer import compose_ledger
from core.db import models
from core.db.repositories import BriefRepository, PlanRepository, SessionRepository
from core.db.session import get_db
from core.schemas import AssumptionLedger, Brief, ExecutionPlan, ValidationReport
from core.state import CampaignState

router = APIRouter(tags=["plans"])


class GeneratePlanResponse(BaseModel):
    plan_id: UUID
    session_id: UUID
    plan: ExecutionPlan
    copy_drafts: dict[str, dict] = {}


@router.post("/briefs/{brief_id}/plan", response_model=GeneratePlanResponse)
async def generate_plan_for_brief(brief_id: UUID, db: DbSession = Depends(get_db)) -> GeneratePlanResponse:
    """Run the P5 plan-generation pipeline against a stored brief and persist the resulting plan."""
    row = BriefRepository(db).get(brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")

    brief = Brief.model_validate(row.parsed_json)
    sid = row.session_id or SessionRepository(db).create(entry_point="plan_from_brief").id
    db.commit()

    state = CampaignState(session_id=sid, entry_point="plan_from_brief", brief=brief)

    from orchestrator.nodes import generate_plan

    state = await generate_plan(state)
    if state.plan is None:
        raise HTTPException(status_code=500, detail="plan generation produced no plan")

    PlanRepository(db).create(state.plan)
    db.commit()

    drafts = load_copy_drafts(sid, state.plan.id)
    return GeneratePlanResponse(
        plan_id=state.plan.id, session_id=sid, plan=state.plan, copy_drafts=drafts
    )


@router.get("/plans/{plan_id}", response_model=ExecutionPlan)
def get_plan(plan_id: UUID, db: DbSession = Depends(get_db)) -> ExecutionPlan:
    row = PlanRepository(db).get(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return ExecutionPlan.model_validate(row.plan_json)


class PlanCopyDraftsResponse(BaseModel):
    plan_id: UUID
    drafts: dict[str, dict]


@router.get("/plans/{plan_id}/copy_drafts", response_model=PlanCopyDraftsResponse)
def get_plan_copy_drafts(plan_id: UUID, db: DbSession = Depends(get_db)) -> PlanCopyDraftsResponse:
    row = db.query(models.ExecutionPlan).filter(models.ExecutionPlan.id == plan_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    brief = db.query(models.Brief).filter(models.Brief.id == row.brief_id).first()
    sid = brief.session_id if brief else None
    drafts = load_copy_drafts(sid, plan_id) if sid else {}
    return PlanCopyDraftsResponse(plan_id=plan_id, drafts=drafts)


# ---------------------------------------------------------------------------
# P6 — Critic + Governance + Ledger + Approval
# ---------------------------------------------------------------------------


def _load_state_for_plan(db: DbSession, plan_id: UUID) -> tuple[CampaignState, models.ExecutionPlan]:
    plan_row = PlanRepository(db).get(plan_id)
    if plan_row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    brief_row = db.query(models.Brief).filter(models.Brief.id == plan_row.brief_id).first()
    if brief_row is None:
        raise HTTPException(status_code=404, detail="brief not found for plan")
    brief = Brief.model_validate(brief_row.parsed_json)
    plan = ExecutionPlan.model_validate(plan_row.plan_json)
    sid = brief_row.session_id
    state = CampaignState(
        session_id=sid or plan.id, entry_point="plan_from_brief", brief=brief, plan=plan
    )
    return state, plan_row


class ReviewResponse(BaseModel):
    plan_id: UUID
    validation_report: ValidationReport
    ledger: AssumptionLedger
    blocking: bool


@router.post("/plans/{plan_id}/review", response_model=ReviewResponse)
async def review_plan(plan_id: UUID, db: DbSession = Depends(get_db)) -> ReviewResponse:
    """Run the Critic + governance scanners + ledger composer against an existing plan."""
    state, plan_row = _load_state_for_plan(db, plan_id)

    from orchestrator.nodes import critic_node, has_blocking_findings, ledger_node

    state = await critic_node(state)
    state = await ledger_node(state)

    # Persist plan status if blocking found.
    blocking = has_blocking_findings(state)
    new_status = "in_review" if blocking else plan_row.status
    if new_status != plan_row.status:
        plan_row.status = new_status
        db.commit()

    # Persist the validation report row (kept simple — one row per /review call).
    if state.validation_report is not None:
        db.add(
            models.ValidationReport(
                id=state.validation_report.id,
                brief_id=state.validation_report.brief_id,
                plan_id=state.validation_report.plan_id,
                report_json=state.validation_report.model_dump(mode="json"),
            )
        )
        db.commit()

    # Persist ledger entries (overwrite-on-replay: delete then insert).
    db.query(models.AssumptionLedger).filter(models.AssumptionLedger.plan_id == plan_id).delete()
    for entry in state.ledger:
        db.add(
            models.AssumptionLedger(
                id=entry.id,
                plan_id=entry.plan_id,
                field_path=entry.field_path,
                assumption_text=entry.assumption_text,
                basis=entry.basis,
                citation=entry.citation,
                confidence=entry.confidence,
                created_by_agent=entry.created_by_agent,
                created_at=entry.created_at,
            )
        )
    db.commit()

    ledger = AssumptionLedger(plan_id=plan_id, entries=state.ledger)
    return ReviewResponse(
        plan_id=plan_id,
        validation_report=state.validation_report,  # type: ignore[arg-type]
        ledger=ledger,
        blocking=blocking,
    )


class ApprovalRequest(BaseModel):
    note: str | None = None


class ApprovalResponse(BaseModel):
    plan_id: UUID
    status: str
    note: str | None = None


@router.post("/plans/{plan_id}/approve", response_model=ApprovalResponse)
def approve_plan(plan_id: UUID, req: ApprovalRequest = ApprovalRequest(), db: DbSession = Depends(get_db)) -> ApprovalResponse:
    repo = PlanRepository(db)
    row = repo.get(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    repo.update_status(plan_id, "approved")
    db.commit()
    return ApprovalResponse(plan_id=plan_id, status="approved", note=req.note)


@router.post("/plans/{plan_id}/reject", response_model=ApprovalResponse)
def reject_plan(plan_id: UUID, req: ApprovalRequest = ApprovalRequest(), db: DbSession = Depends(get_db)) -> ApprovalResponse:
    repo = PlanRepository(db)
    row = repo.get(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    repo.update_status(plan_id, "rejected")
    db.commit()
    return ApprovalResponse(plan_id=plan_id, status="rejected", note=req.note)


class EditRequest(BaseModel):
    field_path: str
    new_value: str  # JSON-stringified for nested values
    note: str | None = None


@router.post("/plans/{plan_id}/edit", response_model=ExecutionPlan)
def edit_plan(plan_id: UUID, req: EditRequest, db: DbSession = Depends(get_db)) -> ExecutionPlan:
    """Apply a simple top-level field edit. For nested edits, supply JSON in `new_value`."""
    import json as _json

    repo = PlanRepository(db)
    row = repo.get(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    data = dict(row.plan_json)
    parts = req.field_path.split(".")
    cursor = data
    for p in parts[:-1]:
        if p not in cursor or not isinstance(cursor[p], dict):
            cursor[p] = {}
        cursor = cursor[p]
    try:
        cursor[parts[-1]] = _json.loads(req.new_value)
    except Exception:
        cursor[parts[-1]] = req.new_value
    row.plan_json = data
    flag_modified(row, "plan_json")
    row.status = "in_review"  # any edit returns to review
    db.commit()
    return ExecutionPlan.model_validate(data)


class LedgerResponse(BaseModel):
    plan_id: UUID
    entries: list[dict]


@router.get("/plans/{plan_id}/ledger", response_model=LedgerResponse)
def get_ledger(plan_id: UUID, db: DbSession = Depends(get_db)) -> LedgerResponse:
    rows = (
        db.query(models.AssumptionLedger)
        .filter(models.AssumptionLedger.plan_id == plan_id)
        .order_by(models.AssumptionLedger.created_at.asc())
        .all()
    )
    if not rows:
        # Synthesize on the fly if not yet persisted.
        state, _ = _load_state_for_plan(db, plan_id)
        ledger = compose_ledger(state)
        return LedgerResponse(
            plan_id=plan_id,
            entries=[e.model_dump(mode="json") for e in ledger.entries],
        )
    return LedgerResponse(
        plan_id=plan_id,
        entries=[
            {
                "id": str(r.id),
                "plan_id": str(r.plan_id),
                "field_path": r.field_path,
                "assumption_text": r.assumption_text,
                "basis": r.basis,
                "citation": r.citation,
                "confidence": float(r.confidence),
                "created_by_agent": r.created_by_agent,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# W2 — Standalone QA (paste brief + plan, get a ValidationReport)
# ---------------------------------------------------------------------------


class StandaloneQARequest(BaseModel):
    brief_text: str
    plan_json: dict


class StandaloneQAResponse(BaseModel):
    validation_report: ValidationReport


@router.post("/qa", response_model=StandaloneQAResponse)
async def standalone_qa(req: StandaloneQARequest) -> StandaloneQAResponse:
    """W2 entry point — accepts a raw brief + a plan JSON and returns a critic report.
    This phase ships a minimal version: the critic runs against the supplied artifacts only.
    Full W2 (with brief normalization) lands in P7."""
    from agents.brief_normalizer import BriefNormalizer
    from agents.critic import Critic
    from core.state import CampaignState
    from uuid import uuid4 as _uuid4

    plan = ExecutionPlan.model_validate(req.plan_json)
    state = CampaignState(session_id=_uuid4(), entry_point="qa_existing_plan", plan=plan)
    state = await BriefNormalizer().run(state, raw_text=req.brief_text, source_format="markdown")
    state = await Critic().run(state)
    if state.validation_report is None:
        raise HTTPException(status_code=500, detail="Critic produced no report")
    return StandaloneQAResponse(validation_report=state.validation_report)
