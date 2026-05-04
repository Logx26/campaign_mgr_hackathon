"""Export an ExecutionPlan as PDF / Markdown / Gantt HTML / JSON.

PDF is the headline format used by the UI (see ``ui/pages/1_Plan_from_Brief.py``).
JSON and Gantt HTML remain available for power-user / developer tooling but
are no longer surfaced in the Streamlit UI."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from agents.copy_drafter import load_copy_drafts
from core.db import models
from core.db.repositories import PlanRepository
from core.db.session import get_db
from core.schemas import ExecutionPlan
from export import (
    export_plan_gantt_html,
    export_plan_json,
    export_plan_markdown,
    export_plan_pdf,
    export_plan_pptx,
)

router = APIRouter(tags=["export"])


def _load_plan_and_drafts(db: DbSession, plan_id: UUID) -> tuple[ExecutionPlan, dict[str, dict]]:
    row = PlanRepository(db).get(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    plan = ExecutionPlan.model_validate(row.plan_json)
    brief = db.query(models.Brief).filter(models.Brief.id == row.brief_id).first()
    sid = brief.session_id if brief else None
    drafts = load_copy_drafts(sid, plan_id) if sid else {}
    return plan, drafts


@router.get("/plans/{plan_id}/export/{fmt}")
def export_plan(
    plan_id: UUID,
    fmt: Literal["json", "markdown", "gantt", "pdf", "pptx"],
    db: DbSession = Depends(get_db),
) -> Response:
    plan, drafts = _load_plan_and_drafts(db, plan_id)

    if fmt == "pptx":
        body = export_plan_pptx(plan, copy_drafts=drafts)
        return Response(
            content=body,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="plan_{plan_id}.pptx"'
            },
        )
    if fmt == "pdf":
        body = export_plan_pdf(plan, copy_drafts=drafts)
        return Response(
            content=body,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="plan_{plan_id}.pdf"'
            },
        )
    if fmt == "json":
        body = export_plan_json(plan, copy_drafts=drafts)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="plan_{plan_id}.json"'},
        )
    if fmt == "markdown":
        body = export_plan_markdown(plan, copy_drafts=drafts)
        return Response(
            content=body,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="plan_{plan_id}.md"'},
        )
    # fmt == "gantt"
    body = export_plan_gantt_html(plan)
    return Response(
        content=body,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="plan_{plan_id}_gantt.html"'},
    )
