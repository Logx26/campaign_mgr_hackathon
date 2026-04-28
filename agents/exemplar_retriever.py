"""A08 — Exemplar Retriever. Pure retrieval; no LLM call."""
from __future__ import annotations

from core.state import CampaignState
from knowledge.exemplar_retriever import retrieve_exemplars


class ExemplarRetriever:
    name = "exemplar_retriever"

    async def run(self, state: CampaignState, *, top_k: int = 3) -> CampaignState:
        if state.brief is None:
            return state
        exemplars = await retrieve_exemplars(state.brief, top_k=top_k)
        # CampaignState.exemplars is list[UUID] — repurpose loosely; we just need to pass them
        # to the planner via a side channel. For now, we attach to a private state cache via
        # model_copy with extra fields disallowed → store as transient context in trace, and
        # return them from this agent for the orchestrator to thread into the planner call.
        return state  # exemplars are retrieved live by the planner node


def get_exemplar_bodies(brief, top_k: int = 3) -> list[str]:
    """Helper used by the planner node."""
    import asyncio

    from knowledge.exemplar_retriever import retrieve_exemplars

    try:
        exemplars = asyncio.get_event_loop().run_until_complete(retrieve_exemplars(brief, top_k=top_k))
    except Exception:
        return []
    return [e.body for e in exemplars]
