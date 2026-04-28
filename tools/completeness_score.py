"""Brief completeness scorer.

Walks `rules/completeness.yaml`, evaluates each rule against the Brief, returns a 0–100
score (weighted) plus the per-rule outcomes that the Completeness Checker turns into Gaps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.rules.loader import load_completeness_rules
from core.schemas import Brief


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule_id: str
    field_path: str
    severity: str
    weight: int
    passed: bool
    description: str
    repair_question: str
    check_type: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_brief(brief: Brief) -> tuple[float, list[RuleOutcome]]:
    """Returns (completeness_score 0-100, per-rule outcomes)."""
    rules = load_completeness_rules()
    outcomes: list[RuleOutcome] = []
    earned = 0
    total = 0

    for rule in rules:
        weight = int(rule.get("weight", 0) or 0)
        total += weight
        passed = _evaluate(brief, rule)
        if passed:
            earned += weight
        outcomes.append(
            RuleOutcome(
                rule_id=str(rule["rule_id"]),
                field_path=str(rule["field_path"]),
                severity=str(rule.get("severity", "soft")),
                weight=weight,
                passed=passed,
                description=str(rule.get("description", "")),
                repair_question=str(rule.get("repair_question", "")),
                check_type=str(rule.get("check_type", "non_empty")),
            )
        )

    score = (earned / total * 100.0) if total > 0 else 0.0
    return round(score, 1), outcomes


# ---------------------------------------------------------------------------
# Field resolution + per-rule predicates
# ---------------------------------------------------------------------------


def _resolve(brief: Brief, field_path: str) -> Any:
    """Walk a dotted path against a Pydantic model. Returns None if any segment is missing."""
    obj: Any = brief
    for part in field_path.split("."):
        if obj is None:
            return None
        if hasattr(obj, part):
            obj = getattr(obj, part)
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return len(value.strip()) == 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _evaluate(brief: Brief, rule: dict) -> bool:
    """Return True if the rule passes (no gap), False if a gap exists."""
    field_path = rule["field_path"]
    check_type = rule.get("check_type", "non_empty")
    value = _resolve(brief, field_path)

    if check_type == "required":
        return value is not None and not _is_empty(value)

    if check_type == "non_empty":
        return not _is_empty(value)

    if check_type == "min_length":
        min_len = int(rule.get("min_length", 1))
        if value is None:
            return False
        return len(str(value).strip()) >= min_len

    if check_type == "numeric_positive":
        if value is None:
            return False
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    if check_type == "present_if":
        # Hand-coded predicates per rule_id — kept explicit because the YAML expression is human prose,
        # not an evaluable DSL. Adding a new present_if rule means adding a branch here.
        rule_id = rule["rule_id"]
        if rule_id == "brief.channels.specific":
            channels = value or []
            vague_terms = {"social", "digital", "online", "web"}
            for ch in channels:
                name = (getattr(ch, "name", None) or (ch.get("name") if isinstance(ch, dict) else "")) or ""
                if name.strip().lower() in vague_terms:
                    return False
            return True
        if rule_id == "brief.success_metrics.baseline":
            metrics = value or []
            for m in metrics:
                baseline = getattr(m, "baseline", None) if not isinstance(m, dict) else m.get("baseline")
                target = getattr(m, "target", None) if not isinstance(m, dict) else m.get("target")
                if baseline is None or target is None:
                    return False
            return len(metrics) > 0
        # Unknown predicate — fail closed (treat as gap) so silent passes don't inflate the score.
        return False

    # Unknown check_type — fail closed.
    return False
