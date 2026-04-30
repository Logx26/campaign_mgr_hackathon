"""POST /qa/by_ids — DB-backed QA without paste.

Mocks `qa_node` so the test is offline and asserts:
  - matched brief_id == plan.brief_id → relationship == "matched"
  - cross_audit brief_id != plan.brief_id → relationship == "cross_audit"
  - 404 when either id is missing
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.db.session import get_db
from core.schemas import Brief, ExecutionPlan, ValidationReport
from core.schemas.brief import AudienceDescription
from core.schemas.plan import CampaignIdentity


def _make_brief(brief_id: UUID) -> Brief:
    return Brief(
        id=brief_id,
        campaign_name="Test Campaign",
        business_objective="grow trial signups",
        target_audience=AudienceDescription(raw_description="enterprise IT leaders"),
        key_message="Faster, safer, smarter.",
        raw_source="Campaign brief body",
        source_format="text",
    )


def _make_plan(brief_id: UUID, plan_id: UUID) -> ExecutionPlan:
    return ExecutionPlan(
        id=plan_id,
        brief_id=brief_id,
        campaign_identity=CampaignIdentity(name="Test Campaign", brief_id=brief_id),
        audience_summary="enterprise IT leaders",
    )


class _FakeBriefRepo:
    def __init__(self, brief_row):
        self._row = brief_row

    def get(self, _id):
        return self._row


class _FakePlanRepo:
    def __init__(self, plan_row):
        self._row = plan_row

    def get(self, _id):
        return self._row


class _FakeDb:
    def add(self, *_a, **_kw):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


def _mock_state_with_report(brief: Brief, plan: ExecutionPlan):
    return SimpleNamespace(
        validation_report=ValidationReport(
            brief_id=brief.id,
            plan_id=plan.id,
            alignment_score=72.0,
            findings=[],
        ),
        plan=plan,
        brief=brief,
    )


@pytest.mark.asyncio
async def test_qa_by_ids_matched_when_brief_owns_plan(monkeypatch):
    brief_id = uuid4()
    plan_id = uuid4()
    brief = _make_brief(brief_id)
    plan = _make_plan(brief_id, plan_id)

    brief_row = SimpleNamespace(
        id=brief_id, session_id=uuid4(), parsed_json=brief.model_dump(mode="json")
    )
    plan_row = SimpleNamespace(
        id=plan_id, brief_id=brief_id, plan_json=plan.model_dump(mode="json")
    )

    from api.routes import plans as plans_route

    monkeypatch.setattr(plans_route, "BriefRepository", lambda _db: _FakeBriefRepo(brief_row))
    monkeypatch.setattr(plans_route, "PlanRepository", lambda _db: _FakePlanRepo(plan_row))

    async def fake_qa_node(state):
        return _mock_state_with_report(brief, plan)

    def fake_blocking(_state):
        return False

    from orchestrator import nodes as orch_nodes
    monkeypatch.setattr(orch_nodes, "qa_node", fake_qa_node)
    monkeypatch.setattr(orch_nodes, "has_blocking_findings", fake_blocking)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    with TestClient(app) as client:
        r = client.post("/api/v1/qa/by_ids", json={"brief_id": str(brief_id), "plan_id": str(plan_id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brief_plan_relationship"] == "matched"
    assert body["validation_report"]["alignment_score"] == 72.0
    assert body["blocking"] is False


@pytest.mark.asyncio
async def test_qa_by_ids_cross_audit_when_plan_was_made_for_other_brief(monkeypatch):
    """User picks brief A and a plan that was generated from brief C — legitimate use of W2.
    The endpoint must respond with relationship='cross_audit' so the UI can disclose it."""
    brief_id = uuid4()
    other_brief_id = uuid4()
    plan_id = uuid4()
    brief = _make_brief(brief_id)
    plan = _make_plan(other_brief_id, plan_id)

    brief_row = SimpleNamespace(
        id=brief_id, session_id=uuid4(), parsed_json=brief.model_dump(mode="json")
    )
    plan_row = SimpleNamespace(
        id=plan_id, brief_id=other_brief_id, plan_json=plan.model_dump(mode="json")
    )

    from api.routes import plans as plans_route

    monkeypatch.setattr(plans_route, "BriefRepository", lambda _db: _FakeBriefRepo(brief_row))
    monkeypatch.setattr(plans_route, "PlanRepository", lambda _db: _FakePlanRepo(plan_row))

    async def fake_qa_node(state):
        return _mock_state_with_report(brief, plan)

    def fake_blocking(_state):
        return False

    from orchestrator import nodes as orch_nodes
    monkeypatch.setattr(orch_nodes, "qa_node", fake_qa_node)
    monkeypatch.setattr(orch_nodes, "has_blocking_findings", fake_blocking)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    with TestClient(app) as client:
        r = client.post("/api/v1/qa/by_ids", json={"brief_id": str(brief_id), "plan_id": str(plan_id)})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brief_plan_relationship"] == "cross_audit"


@pytest.mark.asyncio
async def test_qa_by_ids_404_when_brief_missing(monkeypatch):
    plan_id = uuid4()
    brief_id = uuid4()
    plan = _make_plan(brief_id, plan_id)
    plan_row = SimpleNamespace(
        id=plan_id, brief_id=brief_id, plan_json=plan.model_dump(mode="json")
    )

    from api.routes import plans as plans_route

    monkeypatch.setattr(plans_route, "BriefRepository", lambda _db: _FakeBriefRepo(None))
    monkeypatch.setattr(plans_route, "PlanRepository", lambda _db: _FakePlanRepo(plan_row))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    with TestClient(app) as client:
        r = client.post("/api/v1/qa/by_ids", json={"brief_id": str(brief_id), "plan_id": str(plan_id)})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_qa_by_ids_404_when_plan_missing(monkeypatch):
    brief_id = uuid4()
    plan_id = uuid4()
    brief = _make_brief(brief_id)
    brief_row = SimpleNamespace(
        id=brief_id, session_id=uuid4(), parsed_json=brief.model_dump(mode="json")
    )

    from api.routes import plans as plans_route

    monkeypatch.setattr(plans_route, "BriefRepository", lambda _db: _FakeBriefRepo(brief_row))
    monkeypatch.setattr(plans_route, "PlanRepository", lambda _db: _FakePlanRepo(None))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    with TestClient(app) as client:
        r = client.post("/api/v1/qa/by_ids", json={"brief_id": str(brief_id), "plan_id": str(plan_id)})
    assert r.status_code == 404
