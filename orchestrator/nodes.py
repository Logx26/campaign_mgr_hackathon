"""Node wrappers around agents.

P3: intake + understanding. P4: clarification (in api/routes/briefs.py). P5: plan generation.
"""
from __future__ import annotations

from agents.ambiguity_detector import AmbiguityDetector
from agents.brief_normalizer import BriefNormalizer
from agents.channel_specialist import fan_out_channel_specialists
from agents.completeness_checker import CompletenessChecker
from agents.copy_drafter import fan_out_copy_drafts
from agents.critic import Critic, merge_findings
from agents.governance import run_all_scanners
from agents.ledger_composer import LedgerComposer
from agents.planner import Planner
from agents.timeline_synthesizer import TimelineSynthesizer
from core.state import CampaignState

_brief_normalizer = BriefNormalizer()
_completeness_checker = CompletenessChecker()
_ambiguity_detector = AmbiguityDetector()
_planner = Planner()
_timeline_synthesizer = TimelineSynthesizer()
_critic = Critic()
_ledger_composer = LedgerComposer()


MAX_REVISIONS = 2


async def normalize_node(state: CampaignState, *, raw_text: str, source_format: str = "text") -> CampaignState:
    return await _brief_normalizer.run(state, raw_text=raw_text, source_format=source_format)


async def completeness_node(state: CampaignState) -> CampaignState:
    return await _completeness_checker.run(state)


async def ambiguity_node(state: CampaignState) -> CampaignState:
    return await _ambiguity_detector.run(state)


async def analyze_brief(state: CampaignState) -> CampaignState:
    state = await completeness_node(state)
    state = await ambiguity_node(state)
    return state


# ---------------------------------------------------------------------------
# P5 — Plan generation pipeline
# ---------------------------------------------------------------------------


async def planner_node(state: CampaignState) -> CampaignState:
    return await _planner.run(state)


async def channel_specialist_fanout(state: CampaignState) -> CampaignState:
    return await fan_out_channel_specialists(state)


async def copy_drafter_fanout(state: CampaignState) -> CampaignState:
    return await fan_out_copy_drafts(state)


async def timeline_node(state: CampaignState) -> CampaignState:
    return await _timeline_synthesizer.run(state)


async def generate_plan(state: CampaignState) -> CampaignState:
    """End-to-end plan generation: planner → parallel channel specialists → parallel copy drafts → timeline."""
    state = await planner_node(state)
    state = await channel_specialist_fanout(state)
    state = await copy_drafter_fanout(state)
    state = await timeline_node(state)
    return state


# ---------------------------------------------------------------------------
# P6 — Critic + Governance + Ledger + bounded revision loop
# ---------------------------------------------------------------------------


async def critic_node(state: CampaignState) -> CampaignState:
    """Run LLM Critic + deterministic governance scanners; merge into one ValidationReport."""
    state = await _critic.run(state)
    if state.validation_report is None:
        return state
    governance_findings = run_all_scanners(state)
    if governance_findings:
        merged = merge_findings(state.validation_report, governance_findings)
        state = state.model_copy(update={"validation_report": merged})
    return state


def has_blocking_findings(state: CampaignState) -> bool:
    if state.validation_report is None:
        return False
    return any(f.severity in ("error", "blocker") for f in state.validation_report.findings)


async def ledger_node(state: CampaignState) -> CampaignState:
    return await _ledger_composer.run(state)


async def review_and_revise(state: CampaignState) -> CampaignState:
    """Critic → if blocking + revision_count<2 → re-plan → critic again. Then ledger."""
    state = await critic_node(state)
    while has_blocking_findings(state) and state.revision_count < MAX_REVISIONS:
        state = state.model_copy(update={"revision_count": state.revision_count + 1})
        # Re-plan: keep the brief, regenerate plan from scratch with critic context.
        # For Tier 0 we re-run the full plan pipeline; the critic findings are visible to the
        # planner via state.validation_report (advanced critique injection lands in P7 Tier 1).
        state = await generate_plan(state)
        state = await critic_node(state)
    state = await ledger_node(state)
    return state
