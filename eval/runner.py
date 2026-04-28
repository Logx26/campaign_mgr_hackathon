"""Eval harness runner — skeleton in P2, metric implementations land in P9.

The harness exists from P2 so prompt/agent regressions during P3–P8 are catchable from day 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from core.db import models
from core.db.session import SessionLocal
from eval.golden_set import GoldenItem, load_golden_set


@dataclass(slots=True)
class EvalResult:
    run_id: UUID = field(default_factory=uuid4)
    run_at: datetime = field(default_factory=datetime.utcnow)
    items: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    tag: str | None = None


async def run_item(item: GoldenItem) -> dict[str, Any]:
    """Execute the W1 graph against one golden item. P3+ will provide the graph; for now
    this is a stub that records "not yet executable"."""
    return {
        "item_id": item.item_id,
        "status": "skipped",
        "reason": "agents not yet wired (P3+)",
        "metrics": {},
    }


async def run_all(tag: str | None = None) -> EvalResult:
    """Run every golden item, aggregate metrics, persist an EvalRun row."""
    items = load_golden_set()
    result = EvalResult(tag=tag)
    for item in items:
        result.items.append(await run_item(item))

    # Placeholder summary metrics — P9 implements gap-catch rate / plan-completeness scoring.
    result.summary = {
        "items_total": float(len(items)),
        "items_executed": float(sum(1 for r in result.items if r["status"] == "ok")),
        "items_skipped": float(sum(1 for r in result.items if r["status"] == "skipped")),
        "gap_catch_rate": 0.0,
        "plan_completeness_score": 0.0,
        "assumption_citation_rate": 0.0,
    }

    _persist(result)
    return result


def _persist(result: EvalResult) -> None:
    with SessionLocal() as db:
        row = models.EvalRun(
            id=result.run_id,
            run_at=result.run_at,
            metrics={"summary": result.summary, "items": result.items},
            tag=result.tag,
        )
        db.add(row)
        db.commit()
