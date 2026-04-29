"""P9 demo hardening — fallback payloads + seed scripts shape checks.

Runs purely on the filesystem. No DB / Redis / Azure dependencies.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_DIR = _PROJECT_ROOT / "seeds" / "demo_fallback"


@pytest.mark.parametrize("letter", ["a", "b", "c", "d"])
def test_fallback_payload_present_and_valid_json(letter: str):
    path = _FALLBACK_DIR / f"demo_{letter}.json"
    assert path.is_file(), f"missing fallback for demo {letter}"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["letter"].lower() == letter
    assert payload["title"]
    assert payload["narration"]


def test_fallback_demo_a_has_alignment_and_completeness():
    p = json.loads((_FALLBACK_DIR / "demo_a.json").read_text(encoding="utf-8"))
    assert 0 <= p["alignment_score"] <= 100
    assert 0 <= p["completeness_score"] <= 100
    assert isinstance(p["channels_chosen"], list) and len(p["channels_chosen"]) >= 2
    assert isinstance(p["ledger_excerpt"], list) and p["ledger_excerpt"]


def test_fallback_demo_b_shows_completeness_jump():
    p = json.loads((_FALLBACK_DIR / "demo_b.json").read_text(encoding="utf-8"))
    assert p["completeness_after"] > p["completeness_before"]
    assert isinstance(p["sample_questions"], list) and len(p["sample_questions"]) >= 2


def test_fallback_demo_c_emits_blocker_and_top_findings():
    p = json.loads((_FALLBACK_DIR / "demo_c.json").read_text(encoding="utf-8"))
    assert p["blocking"] is True
    assert p["alignment_score"] < 50
    findings = p["top_findings"]
    assert len(findings) >= 2
    severities = {f["severity"] for f in findings}
    assert "blocker" in severities or "error" in severities


def test_fallback_demo_d_has_terminology_cluster_with_canonical():
    p = json.loads((_FALLBACK_DIR / "demo_d.json").read_text(encoding="utf-8"))
    assert 0.0 <= p["consistency_index"] <= 1.0
    clusters = p["terminology_clusters"]
    assert len(clusters) >= 1
    c = clusters[0]
    assert "AI-powered" in c["variants"] and "AI-assisted" in c["variants"]
    assert c["canonical"] == "AI-assisted"
    assert "brand_book" in c["citation"].lower()


def test_sample_assets_have_3_powered_2_assisted_distribution():
    """The W3 demo is calibrated to 3+2 — guard against silent edits."""
    sample_dir = _PROJECT_ROOT / "seeds" / "sample_assets"
    bodies = []
    for path in sorted(sample_dir.glob("asset_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        bodies.append((data.get("body") or "").lower())
    assert len(bodies) == 5, f"expected exactly 5 sample assets, got {len(bodies)}"
    n_powered = sum("ai-powered" in b for b in bodies)
    n_assisted = sum("ai-assisted" in b for b in bodies)
    assert n_powered == 3, f"expected 3 'AI-powered' assets, got {n_powered}"
    assert n_assisted == 2, f"expected 2 'AI-assisted' assets, got {n_assisted}"


def test_sample_assets_have_3_book_2_schedule_cta_distribution():
    sample_dir = _PROJECT_ROOT / "seeds" / "sample_assets"
    bodies = []
    for path in sorted(sample_dir.glob("asset_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        bodies.append((data.get("body") or "").lower())
    n_book = sum("book a demo" in b for b in bodies)
    n_schedule = sum("schedule a call" in b for b in bodies)
    assert n_book == 3, f"expected 3 'Book a demo' assets, got {n_book}"
    assert n_schedule == 2, f"expected 2 'Schedule a call' assets, got {n_schedule}"


def test_qa_demo_brief_and_plan_files_are_valid():
    qa_dir = _PROJECT_ROOT / "seeds" / "qa_demo"
    brief = (qa_dir / "brief.md").read_text(encoding="utf-8")
    plan = json.loads((qa_dir / "plan.json").read_text(encoding="utf-8"))
    assert "Q3 Enterprise" in brief
    assert plan["status"] == "draft"
    # The plan is intentionally misaligned — should contain at least one prohibited CTA / term marker.
    plan_text = json.dumps(plan).lower()
    assert "click here" in plan_text or "sign up now" in plan_text


@pytest.mark.parametrize("module_name", ["seed_demo_a", "seed_demo_b", "seed_demo_c", "seed_demo_d"])
def test_demo_seed_modules_import_and_define_seed(module_name: str, monkeypatch):
    """Each seed script must define a `seed()` callable. The actual DB/Redis call sites are not
    invoked here — we just confirm the script imports cleanly so a packaging error doesn't kill demo day.
    """
    import sys
    scripts_dir = _PROJECT_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "seed")
    assert callable(mod.seed)
