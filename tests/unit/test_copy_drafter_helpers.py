"""Pure-function helpers from copy_drafter — body sanitization + angle resolution.

These don't touch DB / Redis / Azure, so they run with no infra dependency."""
from __future__ import annotations

from agents.copy_drafter import _derive_angle, _resolve_angle, _sanitize_body


def test_sanitize_strips_control_chars():
    raw = "Hello\x00world\x07!\nNext line\x1f end."
    out = _sanitize_body(raw)
    assert "\x00" not in out
    assert "\x07" not in out
    assert "\x1f" not in out
    assert "Hello" in out and "Next line" in out


def test_sanitize_normalizes_line_endings_and_collapses_blanks():
    raw = "para1\r\n\r\n\r\n\r\npara2\n\n\npara3"
    out = _sanitize_body(raw)
    # Three consecutive blanks should collapse to one.
    assert out.count("\n\n\n") == 0
    assert "para1" in out and "para2" in out and "para3" in out


def test_sanitize_drops_leading_json_fragment():
    raw = '"angle": "ROI-led",\nThe real copy starts here.\nMore text.'
    out = _sanitize_body(raw)
    assert "angle" not in out.split("\n")[0]
    assert "real copy" in out


def test_sanitize_handles_empty_string():
    assert _sanitize_body("") == ""
    assert _sanitize_body(None) == ""  # type: ignore[arg-type]


def test_derive_angle_picks_proof_for_case_study_keyword():
    assert _derive_angle("Our customer story shows a 40% lift in conversions.") == "proof-led"


def test_derive_angle_picks_speed_for_minutes_keyword():
    assert _derive_angle("Replace 3 hours of reconciliation with 10 minutes a week.") == "speed-led"


def test_derive_angle_picks_enterprise_for_enterprise_keyword():
    assert _derive_angle("Built for enterprise revenue teams at 1000+ employee companies.") == "enterprise-led"


def test_derive_angle_falls_back_to_outcome_when_no_keyword_matches():
    assert _derive_angle("A quiet, nondescript paragraph with no signals.") == "outcome-led"


def test_resolve_angle_keeps_meaningful_llm_output():
    assert _resolve_angle("ROI-led", "any body") == "ROI-led"
    assert _resolve_angle("custom-angle-name", "any body") == "custom-angle-name"


def test_resolve_angle_treats_question_mark_and_placeholder_as_missing():
    body = "Our enterprise team..."
    # The pre-fix bug: LLM emitted "?" → UI rendered angle: ?. Now we derive instead.
    assert _resolve_angle("?", body) == "enterprise-led"
    assert _resolve_angle("", body) == "enterprise-led"
    assert _resolve_angle(None, body) == "enterprise-led"
    assert _resolve_angle("n/a", body) == "enterprise-led"
    assert _resolve_angle("TBD", body) == "enterprise-led"


def test_resolve_angle_returns_outcome_when_both_llm_and_body_are_empty():
    assert _resolve_angle("", "") == "outcome-led"
    assert _resolve_angle(None, "") == "outcome-led"
