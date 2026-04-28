"""End-to-end P3: Sample Brief A → ranked GapList with the expected hard/soft gaps surfaced.

Requires Azure chat configured. Skips otherwise.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agents.ambiguity_detector import AmbiguityDetector
from agents.brief_normalizer import BriefNormalizer
from agents.completeness_checker import CompletenessChecker
from core.config import get_settings
from core.state import CampaignState

pytestmark = pytest.mark.integration


def _has_azure_chat() -> bool:
    s = get_settings()
    return bool(s.AZURE_OPENAI_API_KEY and s.AZURE_OPENAI_ENDPOINT and s.AZURE_OPENAI_DEPLOYMENT)


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_sample_brief_a_produces_expected_gaps():
    brief_text = (
        Path(__file__).resolve().parents[2]
        / "seeds"
        / "exemplar_briefs"
        / "b2b_saas_q3_enterprise.md"
    ).read_text(encoding="utf-8")

    state = CampaignState(session_id=uuid4(), entry_point="plan_from_brief")

    state = await BriefNormalizer().run(state, raw_text=brief_text, source_format="markdown")
    assert state.brief is not None
    assert "Q3" in state.brief.campaign_name or "enterprise" in state.brief.campaign_name.lower()

    state = await CompletenessChecker().run(state)
    assert state.gaps is not None
    rule_ids = {g.rule_id for g in state.gaps.gaps if g.rule_id}
    # Brief A intentionally has no budget specified
    assert "brief.budget.total.required" in rule_ids

    state = await AmbiguityDetector().run(state)
    assert state.gaps is not None
    # Should have at least 3 specific gaps total (hard + soft)
    assert len(state.gaps.gaps) >= 3
    # Channels list contains literal "social" — vague-channel rule should fire OR LLM should flag it
    field_paths = {g.field_path for g in state.gaps.gaps}
    assert any(fp.startswith("channels") for fp in field_paths) or "channels" in field_paths
