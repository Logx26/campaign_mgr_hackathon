"""Orchestrator graph (P3 partial).

The full LangGraph graph lands in P4 with HITL interrupts. For P3 we expose a single
async helper `intake_and_analyze` that the API can call directly. This keeps the
phase shippable without committing to LangGraph wiring before clarify is built.
"""
from __future__ import annotations

from core.state import CampaignState
from orchestrator.nodes import analyze_brief, normalize_node


async def intake_and_analyze(
    state: CampaignState,
    *,
    raw_text: str,
    source_format: str = "text",
) -> CampaignState:
    state = await normalize_node(state, raw_text=raw_text, source_format=source_format)
    state = await analyze_brief(state)
    return state
