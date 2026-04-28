"""A07 — Clarifier.

Reads `state.brief` + `state.gaps`, asks the LLM for 3-5 specific typed Questions, returns
state with `state.questions` populated. The Clarifier never blocks — the calling layer
(API + UI) is responsible for the HITL pause and override capture.
"""
from __future__ import annotations

from core.llm.gateway import call_structured
from core.schemas import Question, QuestionListExtraction
from core.state import CampaignState


MAX_QUESTIONS = 5


class Clarifier:
    name = "clarifier"

    async def run(self, state: CampaignState) -> CampaignState:
        if state.brief is None:
            raise ValueError("Clarifier requires state.brief to be set")
        if state.gaps is None or not state.gaps.gaps:
            # Nothing to ask — return state with empty questions list, the caller decides next.
            return state.model_copy(update={"questions": []})

        extraction = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": state.brief.model_dump(mode="json"),
                "gaps_json": state.gaps.model_dump(mode="json"),
            },
            output_schema=QuestionListExtraction,
            session_id=state.session_id,
            agent_name=self.name,
        )

        questions: list[Question] = extraction.to_questions()[:MAX_QUESTIONS]

        # Defensive: drop any question whose gap_id doesn't reference a real gap.
        valid_gap_ids = {g.id for g in state.gaps.gaps}
        questions = [q for q in questions if q.gap_id in valid_gap_ids]

        return state.model_copy(update={"questions": questions})
