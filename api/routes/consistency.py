"""W3 — Multi-asset consistency scan endpoints (P7)."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from agents.copy_drafter import load_copy_drafts
from core.db import models
from core.db.repositories import (
    BriefRepository,
    ConsistencyReportRepository,
    ContentAssetRepository,
    PlanRepository,
)
from core.db.session import get_db
from core.schemas import ConsistencyReport, ExecutionPlan
from orchestrator.nodes import consistency_scan

router = APIRouter(prefix="/consistency", tags=["consistency"])


class AssetIn(BaseModel):
    body: str = Field(..., min_length=1)
    source_name: str | None = None
    channel: str | None = None
    audience_hint: str | None = None


class ScanRequest(BaseModel):
    assets: list[AssetIn] = Field(..., min_length=1, max_length=30)


class ScanResponse(BaseModel):
    report_id: UUID
    asset_ids: list[UUID]
    report: ConsistencyReport


@router.post("/scan", response_model=ScanResponse)
async def scan_assets(req: ScanRequest, db: DbSession = Depends(get_db)) -> ScanResponse:
    """Persist incoming assets, run the W3 pipeline, persist the report, return it."""
    asset_repo = ContentAssetRepository(db)
    rows = [
        asset_repo.create(
            body=a.body,
            source_name=a.source_name,
            channel=a.channel,
            audience_hint=a.audience_hint,
        )
        for a in req.assets
    ]
    db.commit()

    payload = [{"id": r.id, "body": r.body} for r in rows]
    report = await consistency_scan(payload, session_id=uuid4())

    report_row = ConsistencyReportRepository(db).create(
        asset_ids=[r.id for r in rows],
        report_json=report.model_dump(mode="json"),
    )
    db.commit()

    return ScanResponse(
        report_id=report_row.id,
        asset_ids=[r.id for r in rows],
        report=report,
    )


class ScanFromPlanResponse(BaseModel):
    report_id: UUID
    plan_id: UUID
    asset_ids: list[UUID]
    report: ConsistencyReport


@router.post("/scan_from_plan/{plan_id}", response_model=ScanFromPlanResponse)
async def scan_assets_from_plan(plan_id: UUID, db: DbSession = Depends(get_db)) -> ScanFromPlanResponse:
    """Cross-system flex: pull a plan's per-channel copy drafts as the asset set, scan them.

    Demonstrates that W3 audits W1's own outputs — same pipeline, different entry point.
    """
    plan_row = PlanRepository(db).get(plan_id)
    if plan_row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    plan = ExecutionPlan.model_validate(plan_row.plan_json)
    brief_row = db.query(models.Brief).filter(models.Brief.id == plan_row.brief_id).first()
    sid = brief_row.session_id if brief_row else None
    drafts = load_copy_drafts(sid, plan_id) if sid else {}
    if not drafts:
        raise HTTPException(
            status_code=409,
            detail="no copy drafts cached for this plan — run the plan generation pipeline first",
        )

    # Persist a ContentAsset per channel that has a draft.
    asset_repo = ContentAssetRepository(db)
    rows = []
    for ch in plan.channels:
        d = drafts.get(str(ch.id))
        if not d or not d.get("body"):
            continue
        rows.append(
            asset_repo.create(
                body=d["body"],
                source_name=f"plan:{plan_id} / channel:{ch.channel_name}",
                channel=ch.channel_name,
                audience_hint=plan.audience_summary[:240] if plan.audience_summary else None,
            )
        )
    db.commit()

    if not rows:
        raise HTTPException(status_code=409, detail="plan has no copy bodies to scan")

    payload = [{"id": r.id, "body": r.body} for r in rows]
    report = await consistency_scan(payload, session_id=uuid4())

    report_row = ConsistencyReportRepository(db).create(
        asset_ids=[r.id for r in rows],
        report_json=report.model_dump(mode="json"),
    )
    db.commit()

    return ScanFromPlanResponse(
        report_id=report_row.id,
        plan_id=plan_id,
        asset_ids=[r.id for r in rows],
        report=report,
    )


@router.get("/reports/{report_id}", response_model=ConsistencyReport)
def get_report(report_id: UUID, db: DbSession = Depends(get_db)) -> ConsistencyReport:
    row = db.query(models.ConsistencyReport).filter(models.ConsistencyReport.id == report_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="consistency report not found")
    return ConsistencyReport.model_validate(row.report_json)
