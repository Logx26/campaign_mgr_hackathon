"""Governance scanners — deterministic, no LLM."""
from __future__ import annotations

from uuid import uuid4

import pytest

from agents import governance
from core.schemas import (
    AudienceDescription,
    Brief,
    CampaignIdentity,
    ChannelPlan,
    Constraints,
    ExecutionPlan,
)
from core.state import CampaignState


def _state(channel_cta: str = "Book a demo") -> CampaignState:
    brief = Brief(
        campaign_name="Q3",
        business_objective="Convert trials.",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="x",
        constraints=Constraints(mandatory_inclusions=["Customer quote on every asset"]),
        raw_source="(brief)",
    )
    plan = ExecutionPlan(
        brief_id=brief.id,
        campaign_identity=CampaignIdentity(name="Q3 Push", brief_id=brief.id),
        audience_summary="enterprise VPs",
        channels=[
            ChannelPlan(
                channel_name="LinkedIn",
                spec_ref=uuid4(),
                owner_placeholder="[Demand Gen]",
                cta=channel_cta,
            )
        ],
    )
    return CampaignState(session_id=uuid4(), brief=brief, plan=plan)


def test_cta_in_approved_list_passes(monkeypatch):
    monkeypatch.setattr(
        governance,
        "get_channel_spec",
        lambda name: {"name": name, "approved_cta_formats": ["Book a demo"], "prohibited_cta_formats": ["Click here"]},
    )
    findings = governance.scan_cta_against_spec(_state("Book a demo"))
    assert findings == []


def test_cta_prohibited_emits_blocker(monkeypatch):
    monkeypatch.setattr(
        governance,
        "get_channel_spec",
        lambda name: {"name": name, "approved_cta_formats": ["Book a demo"], "prohibited_cta_formats": ["Click here"]},
    )
    findings = governance.scan_cta_against_spec(_state("Click here"))
    assert len(findings) == 1
    assert findings[0].severity == "blocker"
    assert findings[0].category == "compliance"


def test_cta_not_in_approved_list_emits_warning(monkeypatch):
    monkeypatch.setattr(
        governance,
        "get_channel_spec",
        lambda name: {"name": name, "approved_cta_formats": ["Book a demo"], "prohibited_cta_formats": []},
    )
    findings = governance.scan_cta_against_spec(_state("Schedule a call"))
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_prohibited_terms_in_copy(monkeypatch):
    state = _state()
    plan = state.plan
    # Inject a fake copy draft with a prohibited term.
    fake_drafts = {
        str(plan.channels[0].id): {"body": "Our revolutionary platform leverages AI seamlessly."}
    }
    monkeypatch.setattr(governance, "load_copy_drafts", lambda *_a, **_k: fake_drafts)
    monkeypatch.setattr(
        governance,
        "_term_lookup",
        lambda: ({"revolutionary": None, "leverages": "uses", "seamlessly": None}, set()),
    )
    findings = governance.scan_prohibited_terms_in_copy(state)
    assert len(findings) >= 2
    for f in findings:
        assert f.severity == "error"
        assert f.category == "compliance"


def test_copy_length_overrun_emits_warning(monkeypatch):
    state = _state()
    body = "word " * 300  # 300 words
    fake_drafts = {str(state.plan.channels[0].id): {"body": body}}
    monkeypatch.setattr(governance, "load_copy_drafts", lambda *_a, **_k: fake_drafts)
    monkeypatch.setattr(governance, "get_channel_spec", lambda name: {"name": name, "max_length_words": 220})
    findings = governance.scan_copy_length(state)
    # 300 > 220 * 1.15 = 253 → warning
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_mandatory_inclusion_missing_emits_error(monkeypatch):
    state = _state()
    fake_drafts = {str(state.plan.channels[0].id): {"body": "Talk to revenue teams about pipeline."}}
    monkeypatch.setattr(governance, "load_copy_drafts", lambda *_a, **_k: fake_drafts)
    findings = governance.scan_mandatory_inclusions(state)
    # "Customer quote on every asset" → keywords ['customer', 'quote', 'on'] not in body → error.
    assert any(f.severity == "error" and "Customer quote" in f.brief_passage for f in findings)
