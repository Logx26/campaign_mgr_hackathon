"""YAML rule catalog loader.

Rules live in `rules/*.yaml` and are loaded into typed dicts at startup.
Adding a rule requires no code change — just edit the YAML.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RULES_DIR = _PROJECT_ROOT / "rules"


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_completeness_rules() -> list[dict]:
    data = _load_yaml(_RULES_DIR / "completeness.yaml") or {}
    return data.get("rules", [])


@lru_cache(maxsize=1)
def load_budget_norms() -> dict[str, dict]:
    data = _load_yaml(_RULES_DIR / "budget_norms.yaml") or {}
    return {item["channel"]: item for item in data.get("channels", [])}


@lru_cache(maxsize=1)
def load_risk_catalog() -> list[dict]:
    data = _load_yaml(_RULES_DIR / "risk_catalog.yaml") or {}
    return data.get("risks", [])


@lru_cache(maxsize=1)
def load_cta_patterns() -> list[dict]:
    data = _load_yaml(_RULES_DIR / "cta_patterns.yaml") or {}
    return data.get("ctas", [])


@lru_cache(maxsize=1)
def load_channel_dependency_rules() -> list[dict]:
    data = _load_yaml(_RULES_DIR / "channel_dependency_rules.yaml") or {}
    return data.get("channels", [])


def reset_cache() -> None:
    """Clear all caches — used by tests when rules files change between cases."""
    load_completeness_rules.cache_clear()
    load_budget_norms.cache_clear()
    load_risk_catalog.cache_clear()
    load_cta_patterns.cache_clear()
    load_channel_dependency_rules.cache_clear()
