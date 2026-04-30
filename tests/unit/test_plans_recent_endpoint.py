"""GET /plans/recent — read-only listing for UI dropdowns. Same fake-DB pattern as
test_briefs_recent_endpoint.py."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import create_app
from core.db.session import get_db


def _row(name: str, *, status: str = "draft", ts: datetime):
    return SimpleNamespace(
        id=uuid4(),
        brief_id=uuid4(),
        status=status,
        created_at=ts,
        plan_json={"campaign_identity": {"name": name}},
    )


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._limit = None

    def order_by(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def all(self):
        return self._rows[: (self._limit or len(self._rows))]


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def test_recent_plans_returns_campaign_name_from_identity():
    rows = [
        _row("Plan One", status="approved", ts=datetime(2026, 4, 30)),
        _row("Plan Two", status="in_review", ts=datetime(2026, 4, 29)),
    ]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb(rows)
    with TestClient(app) as client:
        r = client.get("/api/v1/plans/recent")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    names = [p["campaign_name"] for p in body]
    assert "Plan One" in names and "Plan Two" in names
    statuses = [p["status"] for p in body]
    assert "approved" in statuses and "in_review" in statuses


def test_recent_plans_handles_missing_identity_gracefully():
    rows = [SimpleNamespace(id=uuid4(), brief_id=uuid4(), status="draft",
                            created_at=datetime(2026, 4, 30), plan_json={})]
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb(rows)
    with TestClient(app) as client:
        r = client.get("/api/v1/plans/recent")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["campaign_name"] == "(untitled plan)"


def test_recent_plans_empty():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: _FakeDb([])
    with TestClient(app) as client:
        r = client.get("/api/v1/plans/recent")
    assert r.status_code == 200
    assert r.json() == []
