"""W2 standalone QA — paste an enterprise brief + an SMB-tone plan, expect coverage /
audience / compliance findings citing concrete passages."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agents.brief_normalizer import BriefNormalizer
from core.config import get_settings
from core.schemas import ExecutionPlan
from core.state import CampaignState
from orchestrator.nodes import has_blocking_findings, qa_node

pytestmark = pytest.mark.integration


def _has_azure_chat() -> bool:
    s = get_settings()
    return bool(s.AZURE_OPENAI_API_KEY and s.AZURE_OPENAI_ENDPOINT and s.AZURE_OPENAI_DEPLOYMENT)


@pytest.mark.skipif(not _has_azure_chat(), reason="Azure chat not configured")
@pytest.mark.asyncio
async def test_w2_qa_emits_alignment_findings_for_mismatched_pair():
    qa_dir = Path(__file__).resolve().parents[2] / "seeds" / "qa_demo"
    brief_text = (qa_dir / "brief.md").read_text(encoding="utf-8")
    plan_obj = json.loads((qa_dir / "plan.json").read_text(encoding="utf-8"))

    plan = ExecutionPlan.model_validate(plan_obj)
    state = CampaignState(session_id=uuid4(), entry_point="qa_existing_plan", plan=plan)
    state = await BriefNormalizer().run(state, raw_text=brief_text, source_format="markdown")
    state = await qa_node(state)

    assert state.validation_report is not None
    assert 0 <= state.validation_report.alignment_score <= 100

    # Mismatch is severe: enterprise brief vs SMB plan, with `Click here` and `Sign up now` CTAs
    # plus prohibited terms 'world-class' / 'seamless' / 'revolutionary' in notes. Expect findings.
    findings = state.validation_report.findings
    assert len(findings) >= 2, f"expected ≥2 findings on mismatched pair, got {len(findings)}"

    # Governance scanners should catch at least one CTA or prohibited-term issue (deterministic).
    rule_ids_or_descriptions = " ".join(
        (f.description + " " + f.plan_section_ref).lower() for f in findings
    )
    assert any(
        kw in rule_ids_or_descriptions
        for kw in ["cta", "click here", "sign up", "prohibited", "world-class", "seamless", "revolutionary"]
    ), f"expected governance scanners to flag CTA/term issues; got: {rule_ids_or_descriptions[:400]}"

    # Mismatched plan should be blocking.
    assert has_blocking_findings(state)
