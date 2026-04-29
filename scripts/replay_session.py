"""Warm Redis caches by replaying every demo flow once end-to-end.

This is the dry-run before judges arrive. After this completes, every demo
prompt is a cache hit — Azure throttling can't kill a live demo.

Usage:
    python scripts/replay_session.py [--with-plan] [--skip a,c]

    --with-plan  also runs generate_plan for demos A and B (more expensive).
    --skip       comma-separated demo letters to skip.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def warm_a_b(brief_path: Path, *, with_plan: bool) -> dict:
    from agents.brief_normalizer import BriefNormalizer
    from core.state import CampaignState
    from orchestrator.nodes import analyze_brief, consistency_scan as _cs  # noqa: F401
    from orchestrator.nodes import generate_plan, qa_node

    raw = brief_path.read_text(encoding="utf-8")
    state = CampaignState(session_id=uuid4(), entry_point="plan_from_brief")
    state = await BriefNormalizer().run(state, raw_text=raw, source_format="markdown")
    state = await analyze_brief(state)
    out: dict = {"brief": brief_path.name, "gaps": len(state.gaps.gaps) if state.gaps else 0}
    if with_plan:
        state = await generate_plan(state)
        state = await qa_node(state)
        out["channels"] = len(state.plan.channels) if state.plan else 0
        out["alignment"] = state.validation_report.alignment_score if state.validation_report else None
    return out


async def warm_c() -> dict:
    """Run /qa-equivalent path against the misaligned demo pair so the LLM cache fills."""
    from agents.brief_normalizer import BriefNormalizer
    from core.schemas import ExecutionPlan
    from core.state import CampaignState
    from orchestrator.nodes import qa_node

    qa_dir = _PROJECT_ROOT / "seeds" / "qa_demo"
    brief_text = (qa_dir / "brief.md").read_text(encoding="utf-8")
    plan_obj = json.loads((qa_dir / "plan.json").read_text(encoding="utf-8"))
    plan = ExecutionPlan.model_validate(plan_obj)
    state = CampaignState(session_id=uuid4(), entry_point="qa_existing_plan", plan=plan)
    state = await BriefNormalizer().run(state, raw_text=brief_text, source_format="markdown")
    state = await qa_node(state)
    return {
        "alignment": state.validation_report.alignment_score if state.validation_report else None,
        "findings": len(state.validation_report.findings) if state.validation_report else 0,
    }


async def warm_d() -> dict:
    """Run W3 consistency scan against the 5 sample assets so embeddings + dictionary stay warm."""
    import yaml as _yaml
    from orchestrator.nodes import consistency_scan

    sample_dir = _PROJECT_ROOT / "seeds" / "sample_assets"
    assets = []
    for path in sorted(sample_dir.glob("asset_*.yaml")):
        data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        body = (data.get("body") or "").strip()
        if body:
            assets.append({"id": uuid4(), "body": body})
    report = await consistency_scan(assets, session_id=uuid4())
    return {
        "n_assets": len(assets),
        "n_terminology_findings": len(report.terminology_findings),
        "n_cta_findings": len(report.cta_findings),
        "consistency_index": report.overall_consistency_index,
    }


async def main(args: argparse.Namespace) -> int:
    skip = {s.strip().lower() for s in (args.skip or "").split(",") if s.strip()}
    out: dict = {}

    if "a" not in skip:
        out["A"] = await warm_a_b(
            _PROJECT_ROOT / "seeds" / "golden_set" / "brief_002.md",
            with_plan=args.with_plan,
        )
    if "b" not in skip:
        out["B"] = await warm_a_b(
            _PROJECT_ROOT / "seeds" / "exemplar_briefs" / "b2b_saas_q3_enterprise.md",
            with_plan=args.with_plan,
        )
    if "c" not in skip:
        out["C"] = await warm_c()
    if "d" not in skip:
        out["D"] = await warm_d()

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Warm caches by replaying every demo flow.")
    parser.add_argument("--with-plan", action="store_true", help="Also run generate_plan for A & B (slow).")
    parser.add_argument("--skip", default="", help="Comma-separated demo letters to skip (e.g. 'a,c').")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
