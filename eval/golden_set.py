"""Loader for the golden-set fixtures used by `eval/runner.py`.

Each golden item is a Markdown brief paired with optional YAML expectation files:
  seeds/golden_set/brief_001.md
  seeds/golden_set/brief_001_expected_gaps.yaml      (optional)
  seeds/golden_set/brief_001_expected_plan_shape.yaml (optional)

P2 ships the loader skeleton + 1 starter brief. P9 fills the set out to 8 items and
implements the metric scoring against expectations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = _PROJECT_ROOT / "seeds" / "golden_set"


@dataclass(frozen=True, slots=True)
class GoldenItem:
    item_id: str  # filename stem, e.g. "brief_001"
    brief_text: str
    expected_gaps: dict[str, Any] = field(default_factory=dict)
    expected_plan_shape: dict[str, Any] = field(default_factory=dict)


def load_golden_set(directory: Path | None = None) -> list[GoldenItem]:
    """Load every `brief_*.md` and pair it with adjacent expectation YAMLs."""
    base = directory or GOLDEN_DIR
    if not base.is_dir():
        return []

    items: list[GoldenItem] = []
    for md_path in sorted(base.glob("brief_*.md")):
        stem = md_path.stem
        text = md_path.read_text(encoding="utf-8")

        gaps_path = base / f"{stem}_expected_gaps.yaml"
        plan_path = base / f"{stem}_expected_plan_shape.yaml"

        gaps = (
            yaml.safe_load(gaps_path.read_text(encoding="utf-8")) or {}
            if gaps_path.is_file()
            else {}
        )
        plan = (
            yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
            if plan_path.is_file()
            else {}
        )
        items.append(
            GoldenItem(
                item_id=stem,
                brief_text=text,
                expected_gaps=gaps,
                expected_plan_shape=plan,
            )
        )
    return items
