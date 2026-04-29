"""Export an ExecutionPlan as pretty-printed JSON."""
from __future__ import annotations

from core.schemas import ExecutionPlan


def export_plan_json(plan: ExecutionPlan, *, copy_drafts: dict[str, dict] | None = None) -> str:
    """Return the plan + (optional) cached copy drafts as a single JSON document."""
    payload = plan.model_dump(mode="json")
    if copy_drafts:
        payload["copy_drafts"] = copy_drafts
    import json

    return json.dumps(payload, indent=2, default=str)
