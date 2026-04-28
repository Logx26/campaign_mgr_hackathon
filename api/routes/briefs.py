"""Brief intake + analysis + clarification endpoints (P3 + P4)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm.attributes import flag_modified

from agents.clarifier import Clarifier
from core.db.repositories import BriefRepository, SessionRepository
from core.db.session import get_db
from core.schemas import Brief, GapList, Question
from core.state import CampaignState
from orchestrator.interrupts import (
    DialogState,
    apply_overrides_to_brief,
    clear_dialog,
    load_dialog,
    save_dialog,
)

router = APIRouter(prefix="/briefs", tags=["briefs"])


class IntakeRequest(BaseModel):
    raw_text: str = Field(..., min_length=10)
    source_format: Literal["text", "markdown", "pdf", "docx", "transcript"] = "text"
    session_id: UUID | None = None


class IntakeResponse(BaseModel):
    brief_id: UUID
    session_id: UUID
    brief: Brief


@router.post("/intake", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
async def intake_brief(req: IntakeRequest, db: DbSession = Depends(get_db)) -> IntakeResponse:
    """Parse raw text into a structured Brief and persist it. Does not analyze gaps yet."""
    sid = req.session_id
    if sid is None:
        sid = SessionRepository(db).create(entry_point="plan_from_brief").id
        db.commit()

    state = CampaignState(session_id=sid, entry_point="plan_from_brief")
    # Reuse the orchestrator node that wraps Brief Normalizer
    from orchestrator.nodes import normalize_node

    state = await normalize_node(state, raw_text=req.raw_text, source_format=req.source_format)
    if state.brief is None:
        raise HTTPException(status_code=500, detail="Brief Normalizer returned no Brief")

    BriefRepository(db).create(state.brief, session_id=sid)
    db.commit()

    return IntakeResponse(brief_id=state.brief.id, session_id=sid, brief=state.brief)


@router.get("/{brief_id}", response_model=Brief)
def get_brief(brief_id: UUID, db: DbSession = Depends(get_db)) -> Brief:
    row = BriefRepository(db).get(brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return Brief.model_validate(row.parsed_json)


class AnalyzeResponse(BaseModel):
    brief_id: UUID
    session_id: UUID
    gaps: GapList


@router.post("/{brief_id}/analyze", response_model=AnalyzeResponse)
async def analyze_brief_endpoint(
    brief_id: UUID,
    db: DbSession = Depends(get_db),
) -> AnalyzeResponse:
    """Run completeness rules + ambiguity detector against a stored Brief."""
    row = BriefRepository(db).get(brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")

    brief = Brief.model_validate(row.parsed_json)
    sid = row.session_id or SessionRepository(db).create(entry_point="plan_from_brief").id
    db.commit()

    state = CampaignState(session_id=sid, entry_point="plan_from_brief", brief=brief)
    from orchestrator.nodes import analyze_brief

    state = await analyze_brief(state)

    if state.gaps is None:
        raise HTTPException(status_code=500, detail="analysis failed to produce a GapList")

    return AnalyzeResponse(brief_id=brief.id, session_id=sid, gaps=state.gaps)


# ---------------------------------------------------------------------------
# P4 — Clarification loop (the differentiator)
# ---------------------------------------------------------------------------


class ClarifyResponse(BaseModel):
    brief_id: UUID
    session_id: UUID
    questions: list[Question]


@router.post("/{brief_id}/clarify", response_model=ClarifyResponse)
async def clarify_brief(brief_id: UUID, db: DbSession = Depends(get_db)) -> ClarifyResponse:
    """Run the analyze pipeline + Clarifier; return 3-5 specific questions.

    Persists the dialog to Redis under `dialog:{session_id}` so a Streamlit rerun resumes
    against the same questions without re-asking the LLM.
    """
    row = BriefRepository(db).get(brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")

    brief = Brief.model_validate(row.parsed_json)
    sid = row.session_id or SessionRepository(db).create(entry_point="plan_from_brief").id
    db.commit()

    state = CampaignState(session_id=sid, entry_point="plan_from_brief", brief=brief)
    from orchestrator.nodes import analyze_brief

    state = await analyze_brief(state)
    state = await Clarifier().run(state)

    save_dialog(
        DialogState(
            session_id=sid,
            brief_id=brief.id,
            questions=state.questions,
            answers={},
        )
    )
    return ClarifyResponse(brief_id=brief.id, session_id=sid, questions=state.questions)


class OverrideAnswer(BaseModel):
    question_id: UUID
    field_path: str
    answer: str
    reason: str | None = None


class OverridesRequest(BaseModel):
    answers: list[OverrideAnswer] = Field(..., min_length=1)


class OverridesResponse(BaseModel):
    brief_id: UUID
    session_id: UUID
    brief: Brief
    overrides_applied: int


@router.post("/{brief_id}/overrides", response_model=OverridesResponse)
def apply_overrides(
    brief_id: UUID,
    req: OverridesRequest,
    db: DbSession = Depends(get_db),
) -> OverridesResponse:
    """Persist user answers as `BriefOverride` rows AND apply them to the parsed brief.

    The original `briefs.raw_source` is never mutated. `briefs.parsed_json` is rewritten
    so the next /analyze sees the enriched view.
    """
    repo = BriefRepository(db)
    row = repo.get(brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")

    brief = Brief.model_validate(row.parsed_json)
    overrides_map: dict[str, str] = {}
    for ans in req.answers:
        repo.add_override(
            brief_id=brief.id,
            field_path=ans.field_path,
            new_value=ans.answer,
            reason=ans.reason,
        )
        overrides_map[ans.field_path] = ans.answer

    updated_brief = apply_overrides_to_brief(brief, overrides_map)
    row.parsed_json = updated_brief.model_dump(mode="json")
    flag_modified(row, "parsed_json")
    db.commit()

    sid = row.session_id
    if sid is not None:
        dialog = load_dialog(sid)
        if dialog is not None:
            for ans in req.answers:
                dialog.answers[str(ans.question_id)] = ans.answer
            dialog.completed = True
            save_dialog(dialog)

    return OverridesResponse(
        brief_id=brief.id,
        session_id=sid or brief.id,
        brief=updated_brief,
        overrides_applied=len(req.answers),
    )


@router.delete("/{brief_id}/clarify", status_code=status.HTTP_204_NO_CONTENT)
def reset_clarification(brief_id: UUID, db: DbSession = Depends(get_db)) -> None:
    """Test/demo helper — clear dialog state for the brief's session."""
    row = BriefRepository(db).get(brief_id)
    if row is None or row.session_id is None:
        return
    clear_dialog(row.session_id)
