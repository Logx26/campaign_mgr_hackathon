"""Eval metrics — gap-catch rate + plan-completeness + assumption-citation rate.

Each metric is a pure function: given (system_output, expected_yaml) → float in [0, 1].
The runner aggregates per-item scores into the EvalRun summary.
"""
from __future__ import annotations

import re
from typing import Any

from core.schemas import ExecutionPlan, GapList


def _normalize(s: str) -> str:
    """Lowercase + strip + collapse whitespace + drop punctuation for fuzzy matching."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9.\s_-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _gap_matches_expectation(gap_field_path: str, gap_desc: str, expected_field: str, expected_desc: str) -> bool:
    """A detected gap is considered to match an expected gap if either:
        - the field paths overlap (share a prefix), OR
        - the description shares a meaningful keyword with the expected description.
    """
    gfp = _normalize(gap_field_path)
    efp = _normalize(expected_field)
    if gfp and efp and (gfp == efp or gfp.startswith(efp) or efp.startswith(gfp)):
        return True
    gd = set(_normalize(gap_desc).split())
    ed = set(_normalize(expected_desc).split())
    # Drop common stopwords so a single shared "the" doesn't count.
    stop = {"the", "a", "an", "is", "in", "of", "to", "and", "or", "for", "on", "by", "with", "as", "no", "not", "any"}
    gd -= stop
    ed -= stop
    if not ed:
        return False
    overlap = gd & ed
    return len(overlap) >= 2


def gap_catch_rate(detected: GapList | None, expected_yaml: dict[str, Any]) -> float:
    """Fraction of expected hard+soft gaps that were detected. 1.0 = all caught."""
    expected = list(expected_yaml.get("hard_gaps") or []) + list(expected_yaml.get("soft_gaps") or [])
    if not expected:
        return 1.0  # No expectations → vacuously perfect.
    if detected is None or not detected.gaps:
        return 0.0

    caught = 0
    for exp in expected:
        ef = exp.get("field_path") or ""
        ed = exp.get("description") or ""
        if any(
            _gap_matches_expectation(g.field_path or "", g.description or "", ef, ed)
            for g in detected.gaps
        ):
            caught += 1
    return caught / len(expected)


def plan_completeness_score(plan: ExecutionPlan | None, expected_yaml: dict[str, Any]) -> float:
    """Fraction of expected plan-shape requirements satisfied.

    Expected YAML may declare:
      min_channels: int
      min_weeks: int
      required_objective_keywords: list[str]   # at least one keyword from each list must appear
      required_channel_names: list[str]
      requires_qa_checkpoint: bool
    """
    if plan is None:
        return 0.0
    if not expected_yaml:
        return 1.0

    checks: list[bool] = []

    min_channels = expected_yaml.get("min_channels")
    if isinstance(min_channels, int):
        checks.append(len(plan.channels) >= min_channels)

    min_weeks = expected_yaml.get("min_weeks")
    if isinstance(min_weeks, int):
        checks.append(len(plan.timeline.weeks) >= min_weeks)

    obj_keywords = expected_yaml.get("required_objective_keywords")
    if isinstance(obj_keywords, list) and obj_keywords:
        objective_text = " ".join(_normalize(o.objective) for o in plan.resolved_objectives)
        checks.append(any(_normalize(k) in objective_text for k in obj_keywords))

    channel_names = expected_yaml.get("required_channel_names")
    if isinstance(channel_names, list) and channel_names:
        plan_channels_lc = {ch.channel_name.lower() for ch in plan.channels}
        checks.append(any(name.lower() in plan_channels_lc for name in channel_names))

    if expected_yaml.get("requires_qa_checkpoint"):
        checks.append(bool(plan.qa_checkpoints))

    if not checks:
        return 1.0
    return sum(1 for c in checks if c) / len(checks)


def assumption_citation_rate(ledger_entries: list) -> float:
    """Fraction of ledger entries that carry a non-empty citation. 1.0 if list is empty."""
    if not ledger_entries:
        return 1.0
    cited = sum(1 for e in ledger_entries if getattr(e, "citation", None))
    return cited / len(ledger_entries)
