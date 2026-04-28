"""A02 — Completeness Checker.

Pure rules, no LLM. Walks `rules/completeness.yaml` against the Brief, emits hard gaps
(severity='hard') for failed required-style rules and soft gaps for failed soft rules.
Also computes the 0-100 completeness score.
"""
from __future__ import annotations

from core.schemas import Brief, Gap, GapList
from core.state import CampaignState
from tools.completeness_score import score_brief


class CompletenessChecker:
    name = "completeness_checker"

    async def run(self, state: CampaignState) -> CampaignState:
        brief: Brief | None = state.brief
        if brief is None:
            raise ValueError("CompletenessChecker requires state.brief to be set")

        score, outcomes = score_brief(brief)

        gaps: list[Gap] = []
        for outcome in outcomes:
            if outcome.passed:
                continue
            gaps.append(
                Gap(
                    field_path=outcome.field_path,
                    severity=outcome.severity,  # 'hard' or 'soft' from YAML
                    source="rule",
                    rule_id=outcome.rule_id,
                    description=outcome.description,
                    suggested_questions=[outcome.repair_question] if outcome.repair_question else [],
                )
            )

        gap_list = GapList(
            gaps=gaps,
            brief_id=brief.id,
            completeness_score=score,
        )
        return state.model_copy(update={"gaps": gap_list})
