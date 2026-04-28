"""Clarifier output: typed questions surfaced to the user."""
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


QuestionType = Literal["single_select", "multi_select", "free_text", "boolean"]


class Question(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    prompt_text: str
    type: QuestionType
    options: list[str] | None = None  # required for single_select / multi_select
    suggested_default: str | None = None
    rationale: str  # why this question matters
    field_path: str  # which Brief field the answer updates
    gap_id: UUID  # links back to source gap


# ---------------------------------------------------------------------------
# LLM-facing extraction shape (drops server-generated `id`)
# ---------------------------------------------------------------------------


class QuestionExtraction(StrictModel):
    prompt_text: str
    type: QuestionType
    options: list[str] | None = None
    suggested_default: str | None = None
    rationale: str
    field_path: str
    gap_id: UUID  # the LLM is given concrete gap UUIDs in the prompt and echoes one back


class QuestionListExtraction(StrictModel):
    questions: list[QuestionExtraction] = Field(default_factory=list)

    def to_questions(self) -> list[Question]:
        return [Question(**q.model_dump()) for q in self.questions]
