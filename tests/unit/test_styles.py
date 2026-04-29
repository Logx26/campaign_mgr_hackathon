"""Smoke tests on the shared style helpers — no Streamlit runtime required."""
from __future__ import annotations

from ui.styles import severity_pill, traffic_color


def test_severity_pill_emits_expected_classes():
    assert "pill-blocker" in severity_pill("blocker")
    assert "pill-error" in severity_pill("error")
    assert "pill-warning" in severity_pill("warning")
    assert "pill-info" in severity_pill("info")
    assert "pill-success" in severity_pill("success")
    # Unknown severity → neutral.
    assert "pill-neutral" in severity_pill("notarealseverity")


def test_severity_pill_accepts_custom_label():
    out = severity_pill("info", "ARMED")
    assert "ARMED" in out
    assert "pill-info" in out
    # No leakage of a literal "info" string when a label is provided.
    assert ">INFO<" not in out


def test_traffic_color_breaks_at_default_thresholds():
    assert traffic_color(85.0) == "var(--success)"
    assert traffic_color(70.0) == "var(--warning)"
    assert traffic_color(20.0) == "var(--danger)"
    # Custom thresholds.
    assert traffic_color(0.92, hi=0.85, mid=0.6) == "var(--success)"
    assert traffic_color(0.7, hi=0.85, mid=0.6) == "var(--warning)"
    assert traffic_color(0.5, hi=0.85, mid=0.6) == "var(--danger)"
