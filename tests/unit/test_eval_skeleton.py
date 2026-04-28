"""Eval harness skeleton — loader works and runner produces a stub result shape."""
from __future__ import annotations

import os

import pytest

from eval.golden_set import load_golden_set
from eval.runner import run_all


def test_golden_set_loads_at_least_brief_001():
    items = load_golden_set()
    ids = {it.item_id for it in items}
    assert "brief_001" in ids
    item = next(it for it in items if it.item_id == "brief_001")
    assert "Q3 Demo Drive" in item.brief_text
    assert "hard_gaps" in item.expected_gaps


@pytest.mark.skipif(
    "POSTGRES_DSN" not in os.environ and not os.environ.get("CI_HAS_PG"),
    reason="No Postgres configured.",
)
@pytest.mark.asyncio
async def test_run_all_returns_summary_and_skips_items():
    result = await run_all(tag="p2-skeleton")
    assert "items_total" in result.summary
    assert result.summary["items_total"] >= 1
    # P2 stub: every item is skipped (agents not yet wired).
    assert all(item["status"] == "skipped" for item in result.items)
