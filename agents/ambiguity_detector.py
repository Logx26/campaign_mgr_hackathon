"""A03 — Ambiguity Detector.

LLM agent. Reads the Brief plus already-found hard gaps; emits soft gaps the rule engine
cannot catch. Output is merged with the rule-based gap list by the orchestrator.
"""
from __future__ import annotations

from core.db.repositories import ChannelSpecRepository
from core.db.session import SessionLocal
from core.llm.gateway import call_structured
from core.schemas import Brief, Gap, GapList, GapListExtraction
from core.state import CampaignState


class AmbiguityDetector:
    name = "ambiguity_detector"

    async def run(self, state: CampaignState) -> CampaignState:
        brief: Brief | None = state.brief
        if brief is None:
            raise ValueError("AmbiguityDetector requires state.brief to be set")

        existing_hard_ids = []
        existing_gaps: list[Gap] = []
        if state.gaps is not None:
            existing_gaps = list(state.gaps.gaps)
            existing_hard_ids = [g.rule_id for g in existing_gaps if g.severity == "hard" and g.rule_id]

        channel_specs_summary = self._channel_specs_summary()

        # Bind the LLM to the extraction shape (no `id` / `computed_at`) — those are
        # server-generated and Azure strict mode would force the LLM to emit `null` for them.
        extraction = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": brief.model_dump(mode="json"),
                "existing_hard_gap_ids": existing_hard_ids,
                "channel_specs_summary": channel_specs_summary,
            },
            output_schema=GapListExtraction,
            session_id=state.session_id,
            agent_name=self.name,
        )

        # Promote extraction → full Gap rows, then defensively coerce shape.
        soft_gaps_raw = extraction.to_gaps()
        cleaned_soft: list[Gap] = []
        for g in soft_gaps_raw:
            cleaned_soft.append(
                g.model_copy(
                    update={
                        "severity": "soft",
                        "source": "llm",
                        "rule_id": None,
                    }
                )
            )

        # Merge: keep the hard rule outcomes, append soft LLM finds, dedupe by (field_path, description).
        merged: list[Gap] = list(existing_gaps)
        seen = {(g.field_path, g.description.strip().lower()) for g in merged}
        for g in cleaned_soft:
            key = (g.field_path, g.description.strip().lower())
            if key in seen:
                continue
            merged.append(g)
            seen.add(key)

        # Preserve the rule-based completeness score; LLM doesn't recompute.
        completeness_score = state.gaps.completeness_score if state.gaps else 0.0
        merged_list = GapList(
            gaps=merged,
            brief_id=brief.id,
            completeness_score=completeness_score,
        )
        return state.model_copy(update={"gaps": merged_list})

    @staticmethod
    def _channel_specs_summary() -> list[dict]:
        try:
            with SessionLocal() as db:
                rows = ChannelSpecRepository(db).list_all()
                return [{"name": r.name, "version": r.version} for r in rows]
        except Exception:
            return []
