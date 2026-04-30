"""Cost meter snapshot + replay shape — built around in-memory fakes since
SessionLocal isn't available without infra."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from observability import cost_meter as cm
from observability import replay as rp


class _FakeRepo:
    def __init__(self, events):
        self._events = events

    def list_for_session(self, _sid):
        return self._events


class _FakeSessionRepo:
    def __init__(self, row):
        self._row = row

    def get(self, _sid):
        return self._row


def _ev(**overrides):
    base = dict(
        id=uuid4(),
        session_id=uuid4(),
        agent_name="test_agent",
        prompt_name="test_agent",
        prompt_version="v1",
        cache_hit=False,
        latency_ms=100,
        tokens_in=50,
        tokens_out=20,
        cost_usd=Decimal("0.001"),
        error=None,
        timestamp=datetime.utcnow(),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_cost_snapshot_aggregates_events(monkeypatch):
    """Cost is summed from trace events, not read from sessions.cost_usd. Live cost in
    Postgres `sessions.cost_usd` is a denormalized counter that may lag the trace rows;
    the events table is the authoritative ledger."""
    sid = uuid4()
    # Stale `sessions.cost_usd` value should be ignored when events have a non-zero sum.
    row = SimpleNamespace(cost_usd=Decimal("0.0001"), status="active")
    events = [
        _ev(latency_ms=200, tokens_in=100, tokens_out=40, cache_hit=False, cost_usd=Decimal("0.0050")),
        _ev(latency_ms=5, tokens_in=0, tokens_out=0, cache_hit=True, cost_usd=Decimal("0")),
        _ev(latency_ms=300, tokens_in=80, tokens_out=30, cache_hit=False, error="boom", cost_usd=Decimal("0.0030")),
    ]

    class _FakeCtx:
        def __enter__(self_):
            return None
        def __exit__(self_, *a):
            return False

    def fake_session_local():
        return _FakeCtx()

    monkeypatch.setattr(cm, "SessionLocal", fake_session_local)
    monkeypatch.setattr(cm, "SessionRepository", lambda _db: _FakeSessionRepo(row))
    monkeypatch.setattr(cm, "TraceRepository", lambda _db: _FakeRepo(events))

    snap = cm.get_cost_snapshot(sid)
    assert snap is not None
    # Authoritative: 0.0050 + 0 + 0.0030 = 0.0080 (NOT the stale 0.0001 on the session row).
    assert snap.cost_usd == Decimal("0.0080")
    assert snap.n_trace_events == 3
    assert snap.n_cache_hits == 1
    assert snap.n_errors == 1
    assert snap.total_tokens_in == 180
    assert snap.total_tokens_out == 70
    assert snap.total_latency_ms == 505
    assert snap.cache_hit_rate() == 1 / 3


def test_cost_snapshot_falls_back_to_session_row_when_events_sum_to_zero(monkeypatch):
    """Legacy sessions might have a value in `sessions.cost_usd` and trace events with
    cost_usd=0 (e.g. all cache hits). In that case prefer the column value so the meter
    isn't reported as $0.0000 when real spend exists."""
    sid = uuid4()
    row = SimpleNamespace(cost_usd=Decimal("0.0123"), status="active")
    events = [
        _ev(cost_usd=Decimal("0"), cache_hit=True),
        _ev(cost_usd=Decimal("0"), cache_hit=True),
    ]

    class _FakeCtx:
        def __enter__(self_):
            return None
        def __exit__(self_, *a):
            return False

    monkeypatch.setattr(cm, "SessionLocal", lambda: _FakeCtx())
    monkeypatch.setattr(cm, "SessionRepository", lambda _db: _FakeSessionRepo(row))
    monkeypatch.setattr(cm, "TraceRepository", lambda _db: _FakeRepo(events))

    snap = cm.get_cost_snapshot(sid)
    assert snap is not None
    assert snap.cost_usd == Decimal("0.0123")


def test_cost_snapshot_returns_none_for_unknown_session(monkeypatch):
    class _FakeCtx:
        def __enter__(self_):
            return None
        def __exit__(self_, *a):
            return False

    monkeypatch.setattr(cm, "SessionLocal", lambda: _FakeCtx())
    monkeypatch.setattr(cm, "SessionRepository", lambda _db: _FakeSessionRepo(None))
    monkeypatch.setattr(cm, "TraceRepository", lambda _db: _FakeRepo([]))

    assert cm.get_cost_snapshot(uuid4()) is None


def test_replay_returns_steps_in_order(monkeypatch):
    sid = uuid4()
    t1 = datetime(2026, 1, 1, 10, 0, 0)
    t2 = datetime(2026, 1, 1, 10, 0, 5)
    events = [
        _ev(timestamp=t1, agent_name="a", cache_hit=False),
        _ev(timestamp=t2, agent_name="b", cache_hit=True, latency_ms=2),
    ]

    class _FakeCtx:
        def __enter__(self_):
            return None
        def __exit__(self_, *a):
            return False

    monkeypatch.setattr(rp, "SessionLocal", lambda: _FakeCtx())
    monkeypatch.setattr(rp, "TraceRepository", lambda _db: _FakeRepo(events))

    steps = rp.replay_session(sid)
    assert len(steps) == 2
    assert steps[0].agent_name == "a"
    assert steps[1].cache_hit is True
    assert steps[1].latency_ms == 2
