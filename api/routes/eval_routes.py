"""Eval read endpoints — the dashboard polls /api/v1/eval/runs."""
from __future__ import annotations

from fastapi import APIRouter

from eval.runner import list_runs

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/runs")
def get_runs(limit: int = 50) -> list[dict]:
    return list_runs(limit=limit)
