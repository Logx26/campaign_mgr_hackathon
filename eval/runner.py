"""Eval harness runner.

P2 shipped the skeleton; P8 wires the real graph in. Each golden item is run end-to-end
through the analyze pipeline (and optionally the plan pipeline if the expectations need
plan-shape scoring), the outputs scored against expected_*.yaml, and one EvalRun row is
written per `run_all` invocation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from core.db import models
from core.db.session import SessionLocal
from core.state import CampaignState
from eval.golden_set import GoldenItem, load_golden_set
from eval.metrics import gap_catch_rate, plan_completeness_score


@dataclass(slots=True)
class EvalResult:
    run_id: UUID = field(default_factory=uuid4)
    run_at: datetime = field(default_factory=datetime.utcnow)
    items: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    tag: str | None = None


def _expected_completeness_max(expected_gaps: dict[str, Any]) -> float | None:
    val = expected_gaps.get("expected_completeness_score_max")
    if isinstance(val, (int, float)):
        return float(val)
    return None


async def run_item(item: GoldenItem, *, with_plan: bool = False) -> dict[str, Any]:
    """Execute the analyze pipeline (and optionally generate_plan) against one golden item."""
    from agents.brief_normalizer import BriefNormalizer
    from orchestrator.nodes import analyze_brief, generate_plan

    metrics_out: dict[str, float] = {}
    error: str | None = None
    try:
        state = CampaignState(session_id=uuid4(), entry_point="plan_from_brief")
        state = await BriefNormalizer().run(state, raw_text=item.brief_text, source_format="markdown")
        state = await analyze_brief(state)
        metrics_out["gap_catch_rate"] = gap_catch_rate(state.gaps, item.expected_gaps)
        metrics_out["n_gaps_detected"] = float(len(state.gaps.gaps) if state.gaps else 0)

        if with_plan and item.expected_plan_shape:
            state = await generate_plan(state)
            metrics_out["plan_completeness"] = plan_completeness_score(state.plan, item.expected_plan_shape)

        return {
            "item_id": item.item_id,
            "status": "ok",
            "metrics": metrics_out,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return {
            "item_id": item.item_id,
            "status": "error",
            "metrics": metrics_out,
            "error": error,
        }


async def run_all(tag: str | None = None, *, with_plan: bool = False) -> EvalResult:
    """Run every golden item, aggregate metrics, persist an EvalRun row."""
    items = load_golden_set()
    result = EvalResult(tag=tag)
    for item in items:
        result.items.append(await run_item(item, with_plan=with_plan))

    # Aggregate
    ok_items = [r for r in result.items if r["status"] == "ok"]
    catch_scores = [r["metrics"]["gap_catch_rate"] for r in ok_items if "gap_catch_rate" in r["metrics"]]
    plan_scores = [r["metrics"]["plan_completeness"] for r in ok_items if "plan_completeness" in r["metrics"]]

    result.summary = {
        "items_total": float(len(items)),
        "items_executed": float(len(ok_items)),
        "items_skipped": float(sum(1 for r in result.items if r["status"] == "skipped")),
        "items_errored": float(sum(1 for r in result.items if r["status"] == "error")),
        "gap_catch_rate": (sum(catch_scores) / len(catch_scores)) if catch_scores else 0.0,
        "plan_completeness_score": (sum(plan_scores) / len(plan_scores)) if plan_scores else 0.0,
    }

    _persist(result)
    return result


def _persist(result: EvalResult) -> None:
    try:
        with SessionLocal() as db:
            row = models.EvalRun(
                id=result.run_id,
                run_at=result.run_at,
                metrics={"summary": result.summary, "items": result.items},
                tag=result.tag,
            )
            db.add(row)
            db.commit()
    except Exception:
        # DB optional in CI / offline runs; log only.
        import logging
        logging.getLogger("eval.runner").exception("eval persist failed")


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Read recent EvalRun rows for the dashboard."""
    try:
        with SessionLocal() as db:
            rows = (
                db.query(models.EvalRun)
                .order_by(models.EvalRun.run_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": str(r.id),
                    "run_at": r.run_at.isoformat(),
                    "tag": r.tag,
                    "summary": (r.metrics or {}).get("summary", {}),
                }
                for r in rows
            ]
    except Exception:
        return []
