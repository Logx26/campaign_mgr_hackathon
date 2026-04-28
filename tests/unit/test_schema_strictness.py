"""Schema contract tests — every Tier 0 schema must reject unknown keys (extra='forbid').

This is mandatory for Azure OpenAI Structured Outputs (json_schema with strict=True).
A regression here means structured-output calls will silently allow extra fields.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.schemas import (
    AssumptionLedger,
    AudienceDescription,
    Brief,
    BrandVoiceFingerprint,
    CanonicalSuggestion,
    ChannelPlan,
    ChannelSpec,
    ConsistencyReport,
    CopyDraft,
    CTAFinding,
    ExecutionPlan,
    Gap,
    GapList,
    LedgerEntry,
    Question,
    TerminologyFinding,
    TraceEvent,
    ValidationFinding,
    ValidationReport,
)
from core.schemas.plan import CampaignIdentity
from core.state import CampaignState


SCHEMAS_TO_TEST = [
    Brief,
    Gap,
    GapList,
    Question,
    ChannelSpec,
    ChannelPlan,
    ExecutionPlan,
    CopyDraft,
    LedgerEntry,
    AssumptionLedger,
    ValidationFinding,
    ValidationReport,
    TerminologyFinding,
    CTAFinding,
    CanonicalSuggestion,
    ConsistencyReport,
    BrandVoiceFingerprint,
    TraceEvent,
    CampaignState,
    AudienceDescription,
]


@pytest.mark.parametrize("schema_cls", SCHEMAS_TO_TEST)
def test_schema_rejects_unknown_key(schema_cls):
    """Every typed schema must raise on an unknown key."""
    payload = {"__definitely_not_a_field__": "x"}
    with pytest.raises(ValidationError):
        schema_cls.model_validate(payload)


def test_brief_round_trips_json():
    brief = Brief(
        campaign_name="Test",
        business_objective="Drive demos",
        target_audience=AudienceDescription(raw_description="enterprise VPs"),
        key_message="Stop reporting on yesterday",
        raw_source="raw text",
    )
    js = brief.model_dump_json()
    restored = Brief.model_validate_json(js)
    assert restored.campaign_name == brief.campaign_name
    assert restored.id == brief.id


def test_execution_plan_minimal_construction():
    brief_id = uuid4()
    plan = ExecutionPlan(
        brief_id=brief_id,
        campaign_identity=CampaignIdentity(name="Test", brief_id=brief_id),
        audience_summary="enterprise VPs",
    )
    assert plan.status == "draft"
    assert plan.version == 1


def test_gap_list_clamps_completeness_score():
    with pytest.raises(ValidationError):
        GapList(gaps=[], brief_id=uuid4(), completeness_score=150.0)


def test_validation_finding_severity_enum():
    with pytest.raises(ValidationError):
        ValidationFinding(
            category="coverage",
            severity="catastrophic",  # not in literal
            brief_passage="x",
            plan_section_ref="y",
            description="z",
            suggested_fix="fix",
        )


def test_trace_event_defaults():
    ev = TraceEvent(session_id=uuid4(), agent_name="test", input_hash="0" * 64)
    assert ev.tokens_in == 0
    assert ev.cache_hit is False
    assert isinstance(ev.timestamp, datetime)
