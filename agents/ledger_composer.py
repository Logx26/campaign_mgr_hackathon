"""A15 — Ledger Composer.

Pure template: walks the brief, gaps, overrides, plan, and channel-specialist outputs to
produce one `LedgerEntry` per assumption with citation. No LLM calls.
"""
from __future__ import annotations

from datetime import datetime

from agents.copy_drafter import load_copy_drafts
from core.schemas import AssumptionLedger, Brief, ExecutionPlan, LedgerEntry
from core.state import CampaignState


def compose_ledger(state: CampaignState) -> AssumptionLedger:
    """Build an `AssumptionLedger` from current state. Idempotent."""
    if state.plan is None:
        return AssumptionLedger(plan_id=__import__("uuid").uuid4(), entries=[])

    plan: ExecutionPlan = state.plan
    brief: Brief | None = state.brief
    entries: list[LedgerEntry] = []
    now = datetime.utcnow()

    # 1. Resolved objectives — each binds to brief objectives or planner inference.
    for obj in plan.resolved_objectives:
        basis = "user_input" if brief and brief.business_objective and obj.objective in brief.business_objective else "llm_inference"
        entries.append(
            LedgerEntry(
                plan_id=plan.id,
                field_path="resolved_objectives",
                assumption_text=f"Treat objective '{obj.objective}' as addressed by channels: {', '.join(obj.addressed_by_channels) or '(none specified)'}",
                basis=basis,
                citation=("brief.business_objective" if basis == "user_input" else "Planner inference from brief context"),
                confidence=0.85 if basis == "user_input" else 0.65,
                created_by_agent="planner",
                created_at=now,
            )
        )

    # 2. Channels — each binds to either user channel list or planner choice.
    user_channels = [c.name.lower() for c in (brief.channels if brief else [])]
    for ch in plan.channels:
        in_brief = any(ch.channel_name.lower() in u or u in ch.channel_name.lower() for u in user_channels)
        entries.append(
            LedgerEntry(
                plan_id=plan.id,
                field_path=f"channels[{ch.channel_name}]",
                assumption_text=f"Use {ch.channel_name} with CTA '{ch.cta}'",
                basis="user_input" if in_brief else "rule",
                citation=(
                    f"brief.channels (user-listed)" if in_brief else f"channel_spec_library.{ch.channel_name}"
                ),
                confidence=0.9 if in_brief else 0.7,
                created_by_agent="planner",
                created_at=now,
            )
        )

    # 3. Brief overrides — each user clarification answer.
    if brief:
        for ov in brief.overrides:
            entries.append(
                LedgerEntry(
                    plan_id=plan.id,
                    field_path=ov.field_path,
                    assumption_text=f"Field '{ov.field_path}' set to '{ov.new_value}' by user clarification.",
                    basis="user_input",
                    citation=f"brief_override:{ov.id}",
                    confidence=1.0,
                    created_by_agent="clarifier",
                    created_at=ov.created_at,
                )
            )

    # 4. Copy drafts — each per-channel draft is an LLM inference.
    drafts = load_copy_drafts(state.session_id, plan.id)
    for ch in plan.channels:
        d = drafts.get(str(ch.id))
        if not d:
            continue
        entries.append(
            LedgerEntry(
                plan_id=plan.id,
                field_path=f"channels[{ch.channel_name}].copy_draft",
                assumption_text=(
                    f"Drafted {ch.channel_name} copy using angle '{d.get('angle', '?')}', "
                    f"voice score {d.get('voice_score', 0):.0f}/100."
                ),
                basis="llm_inference",
                citation=f"copy_drafter:{ch.channel_name} + brand_voice_fingerprint",
                confidence=0.7,
                created_by_agent="copy_drafter",
                created_at=now,
            )
        )

    # 5. Timeline dependencies — each rule-based string is a deterministic assumption.
    for dep in plan.timeline.dependencies:
        entries.append(
            LedgerEntry(
                plan_id=plan.id,
                field_path="timeline.dependencies",
                assumption_text=dep,
                basis="rule",
                citation="rules/channel_dependency_rules.yaml",
                confidence=0.95,
                created_by_agent="timeline_synthesizer",
                created_at=now,
            )
        )

    # 6. QA checkpoints + success metric bindings — usually planner-emitted.
    for qa in plan.qa_checkpoints:
        entries.append(
            LedgerEntry(
                plan_id=plan.id,
                field_path="qa_checkpoints",
                assumption_text=f"{qa.name} scheduled at week {qa.occurs_at_week or '?'}: {qa.description}",
                basis="llm_inference",
                citation="planner",
                confidence=0.75,
                created_by_agent="planner",
                created_at=now,
            )
        )

    return AssumptionLedger(plan_id=plan.id, entries=entries, composed_at=now)


class LedgerComposer:
    name = "ledger_composer"

    async def run(self, state: CampaignState) -> CampaignState:
        ledger = compose_ledger(state)
        return state.model_copy(update={"ledger": ledger.entries})
