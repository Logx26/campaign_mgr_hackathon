"""End-to-end P6: Sample Brief A → plan → critic + governance + ledger."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agents.brief_normalizer import BriefNormalizer
from core.config import get_settings
from core.state import CampaignState
from orchestrator.nodes import critic_node, generate_plan, ledger_node

pytestmark = pytest.mark.integration


def _has_azure_chat() -> bool:
    s = get_settings()
    return bool(s.AZURE_OPENAI_API_KEY and s.AZURE_OPENAI_ENDPOINT and s.AZURE_OPENAI_DEPLOYMENT)


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_critic_and_ledger_for_sample_brief_a():
    brief_text = (
        Path(__file__).resolve().parents[2]
        / "seeds"
        / "exemplar_briefs"
        / "b2b_saas_q3_enterprise.md"
    ).read_text(encoding="utf-8")

    state = CampaignState(session_id=uuid4(), entry_point="plan_from_brief")
    state = await BriefNormalizer().run(state, raw_text=brief_text, source_format="markdown")
    state = await generate_plan(state)
    state = await critic_node(state)
    state = await ledger_node(state)

    assert state.validation_report is not None
    assert 0 <= state.validation_report.alignment_score <= 100
    # Ledger should have entries for objectives + each channel + each copy draft + dependencies + QA.
    assert len(state.ledger) >= 5
    # Each entry must carry a citation.
    for e in state.ledger:
        assert e.citation
