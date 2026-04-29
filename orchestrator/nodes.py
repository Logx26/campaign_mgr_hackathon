"""Node wrappers around agents.

P3: intake + understanding. P4: clarification (in api/routes/briefs.py). P5: plan generation.
P7: consistency scan (W3) + governance-merged QA (W2).
"""
from __future__ import annotations

from uuid import UUID

from agents.ambiguity_detector import AmbiguityDetector
from agents.brief_normalizer import BriefNormalizer
from agents.canonical_resolver import CanonicalResolver
from agents.channel_specialist import fan_out_channel_specialists
from agents.completeness_checker import CompletenessChecker
from agents.consistency_report_composer import compose_report
from agents.copy_drafter import fan_out_copy_drafts
from agents.critic import Critic, merge_findings
from agents.cta_scanner import CTAScanner
from agents.governance import run_all_scanners
from agents.ledger_composer import LedgerComposer
from agents.planner import Planner
from agents.terminology_scanner import TerminologyScanner
from agents.timeline_synthesizer import TimelineSynthesizer
from core.schemas import ConsistencyReport
from core.state import CampaignState

_brief_normalizer = BriefNormalizer()
_completeness_checker = CompletenessChecker()
_ambiguity_detector = AmbiguityDetector()
_planner = Planner()
_timeline_synthesizer = TimelineSynthesizer()
_critic = Critic()
_ledger_composer = LedgerComposer()
_terminology_scanner = TerminologyScanner()
_cta_scanner = CTAScanner()
_canonical_resolver = CanonicalResolver()


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


# ---------------------------------------------------------------------------
# P7 — W2 standalone QA (governance-merged)
# ---------------------------------------------------------------------------


async def qa_node(state: CampaignState) -> CampaignState:
    """W2 helper: run Critic + governance scanners against an already-loaded brief + plan.

    Differs from `critic_node` only in semantic intent — separate name so the W2 path is
    auditable in trace events. Reused by the standalone /qa endpoint.
    """
    state = await _critic.run(state)
    if state.validation_report is None:
        return state
    governance_findings = run_all_scanners(state)
    if governance_findings:
        merged = merge_findings(state.validation_report, governance_findings)
        state = state.model_copy(update={"validation_report": merged})
    return state


# ---------------------------------------------------------------------------
# P7 — W3 multi-asset consistency scan
# ---------------------------------------------------------------------------


async def consistency_scan(
    assets: list[dict],
    *,
    session_id: UUID | None = None,
) -> ConsistencyReport:
    """End-to-end W3 pipeline: terminology + CTA scanners → canonical resolver → composer.

    `assets` is a list of {id: UUID|str, body: str, channel?: str, audience_hint?: str}.
    """
    if not assets:
        return ConsistencyReport(asset_refs=[], overall_consistency_index=1.0)

    # Run scanners (deterministic; no LLM by default, LLM only in CTAScanner fallback path).
    terminology = await _terminology_scanner.run(assets, session_id=session_id)
    cta = await _cta_scanner.run(assets, session_id=session_id)
    suggestions = await _canonical_resolver.run(terminology, session_id=session_id)

    asset_ids: list[UUID] = []
    for a in assets:
        aid = a.get("id")
        if isinstance(aid, str):
            asset_ids.append(UUID(aid))
        elif isinstance(aid, UUID):
            asset_ids.append(aid)

    return compose_report(
        asset_ids=asset_ids,
        terminology=terminology,
        cta=cta,
        suggestions=suggestions,
    )
