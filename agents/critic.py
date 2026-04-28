"""A14 — Critic. Plan-brief alignment check. Used in W1 revision loop AND W2 standalone QA."""
from __future__ import annotations

import json

from agents.copy_drafter import load_copy_drafts
from core.llm.gateway import call_structured
from core.schemas import (
    Brief,
    ExecutionPlan,
    ValidationFinding,
    ValidationReport,
    ValidationReportExtraction,
)
from core.state import CampaignState


class Critic:
    name = "critic"

    async def run(self, state: CampaignState) -> CampaignState:
        if state.brief is None or state.plan is None:
            raise ValueError("Critic requires both state.brief and state.plan to be set")

        copy_drafts = self._collect_copy_drafts(state)

        extraction = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": state.brief.model_dump(mode="json"),
                "plan_json": state.plan.model_dump(mode="json"),
                "copy_drafts": copy_drafts,
            },
            output_schema=ValidationReportExtraction,
            session_id=state.session_id,
            agent_name=self.name,
        )

        report = ValidationReport(
            brief_id=state.brief.id,
            plan_id=state.plan.id,
            alignment_score=extraction.alignment_score,
            findings=[ValidationFinding(**f.model_dump()) for f in extraction.findings],
        )
        return state.model_copy(update={"validation_report": report})

    @staticmethod
    def _collect_copy_drafts(state: CampaignState) -> list[dict]:
        if state.plan is None:
            return []
        cached = load_copy_drafts(state.session_id, state.plan.id)
        result: list[dict] = []
        for ch in state.plan.channels:
            d = cached.get(str(ch.id))
            if not d:
                continue
            body = d.get("body", "")
            if len(body) > 1200:
                body = body[:1200] + "…"
            result.append(
                {
                    "channel_name": ch.channel_name,
                    "cta": ch.cta,
                    "voice_score": d.get("voice_score"),
                    "angle": d.get("angle"),
                    "body": body,
                }
            )
        return result


def merge_findings(report: ValidationReport, extra: list[ValidationFinding]) -> ValidationReport:
    """Append deterministic governance findings to a Critic-emitted report and rescore."""
    combined = list(report.findings) + list(extra)
    # Re-sort by severity (blocker > error > warning > info).
    sev_rank = {"blocker": 0, "error": 1, "warning": 2, "info": 3}
    combined.sort(key=lambda f: sev_rank.get(f.severity, 99))

    # Penalize alignment_score for any new error/blocker rule findings.
    score = report.alignment_score
    for f in extra:
        if f.severity == "blocker":
            score -= 15
        elif f.severity == "error":
            score -= 8
        elif f.severity == "warning":
            score -= 3
    score = max(0.0, min(100.0, score))

    return report.model_copy(update={"findings": combined, "alignment_score": round(score, 1)})
