"""A01 — Brief Normalizer.

Raw text → structured `Brief`. One LLM call per run.
"""
from __future__ import annotations

from core.llm.gateway import call_structured
from core.schemas import BriefExtraction
from core.state import CampaignState


class BriefNormalizer:
    name = "brief_normalizer"

    async def run(self, state: CampaignState, *, raw_text: str, source_format: str = "text") -> CampaignState:
        # Bind the LLM to BriefExtraction (no `id` / `created_at` / `overrides`) — those
        # are server-generated and the LLM would emit `null`, which fails Brief's UUID type.
        extraction = await call_structured(
            prompt_name=self.name,
            variables={"raw_text": raw_text, "source_format": source_format},
            output_schema=BriefExtraction,
            session_id=state.session_id,
            agent_name=self.name,
        )

        # Trust caller input for raw_source + source_format if the LLM dropped/changed them.
        updates: dict = {}
        if not extraction.raw_source:
            updates["raw_source"] = raw_text
        if extraction.source_format != source_format:
            updates["source_format"] = source_format
        if updates:
            extraction = extraction.model_copy(update=updates)

        brief = extraction.to_brief()
        return state.model_copy(update={"brief": brief})
