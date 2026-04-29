"""Shared Streamlit styling — palette, gradient banners, status pills, error callouts.

Every page calls `inject_global_css()` once after `st.set_page_config`. The CSS lives in
this module (not on disk) so we can ship the UI as a pure pip-installed package later.

Palette (ADR-007 — Axion demo theme, P9):
    --bg-deep:    #0F1623   page canvas
    --bg-panel:   #172033   panels / cards
    --bg-soft:    #1F2A40   raised surfaces (hover, callouts)
    --text-1:     #E6ECF3   primary text
    --text-2:     #A6B0C0   muted text
    --accent:     #FF6B5B   primary CTA / live values
    --accent-2:   #FFA94D   secondary accent (gradient stop)
    --success:    #2BD68A
    --warning:    #F2C94C
    --danger:     #FF5C7A
    --info:       #6FB3F2
"""
from __future__ import annotations

from typing import Literal

import streamlit as st


_GLOBAL_CSS = """
<style>
:root {
    --bg-deep: #0F1623;
    --bg-panel: #172033;
    --bg-soft: #1F2A40;
    --text-1: #E6ECF3;
    --text-2: #A6B0C0;
    --accent: #FF6B5B;
    --accent-2: #FFA94D;
    --success: #2BD68A;
    --warning: #F2C94C;
    --danger: #FF5C7A;
    --info: #6FB3F2;
    --border: #25324B;
}

/* Headlines — tighter tracking + slightly heavier weight */
h1, h2, h3 {
    letter-spacing: -0.01em;
    color: var(--text-1) !important;
}
h1 { font-weight: 700 !important; }
h2 { font-weight: 650 !important; }

/* Gradient hero banner */
.axion-banner {
    background: linear-gradient(135deg, #FF6B5B 0%, #FFA94D 60%, #6FB3F2 130%);
    padding: 22px 28px;
    border-radius: 14px;
    margin: 4px 0 22px 0;
    box-shadow: 0 6px 24px rgba(255, 107, 91, 0.18);
    color: #0F1623;
}
.axion-banner h1 {
    margin: 0 0 6px 0;
    color: #0F1623 !important;
    font-size: 1.6rem;
    font-weight: 700;
}
.axion-banner p {
    margin: 0;
    color: #1A2236;
    font-size: 0.95rem;
    line-height: 1.4;
    max-width: 880px;
}

/* Phase-tag chips beside the banner header */
.axion-tag {
    display: inline-block;
    background: rgba(15, 22, 35, 0.18);
    color: #0F1623;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 3px 10px;
    border-radius: 999px;
    margin-right: 6px;
    vertical-align: middle;
}

/* Severity / status pills */
.pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid transparent;
    line-height: 1.5;
}
.pill-info    { background: rgba(111,179,242,0.12); color: var(--info); border-color: rgba(111,179,242,0.4); }
.pill-success { background: rgba(43,214,138,0.12); color: var(--success); border-color: rgba(43,214,138,0.4); }
.pill-warning { background: rgba(242,201,76,0.14); color: var(--warning); border-color: rgba(242,201,76,0.45); }
.pill-error   { background: rgba(255,92,122,0.14); color: var(--danger); border-color: rgba(255,92,122,0.45); }
.pill-blocker { background: var(--danger); color: #fff; border-color: var(--danger); }
.pill-neutral { background: rgba(166,176,192,0.12); color: var(--text-2); border-color: rgba(166,176,192,0.3); }

/* Plain card wrapper — used for plan/channel sections */
.axion-card {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 12px;
}
.axion-card h4 { margin: 0 0 6px 0; color: var(--text-1); font-size: 1rem; }

/* Inline metric strip (when plain st.metric needs framing) */
.metric-strip {
    display: flex; gap: 10px; flex-wrap: wrap;
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 12px;
}
.metric-strip .metric-cell {
    min-width: 120px;
}
.metric-strip .metric-label {
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 2px;
}
.metric-strip .metric-value {
    color: var(--text-1);
    font-size: 1.3rem;
    font-weight: 600;
}

/* Friendly error callout — never shows a raw stack trace */
.axion-error {
    background: rgba(255,92,122,0.08);
    border: 1px solid rgba(255,92,122,0.35);
    color: var(--danger);
    padding: 12px 16px;
    border-radius: 10px;
    margin: 10px 0;
    font-size: 0.88rem;
}
.axion-error .axion-error-title { font-weight: 700; margin-bottom: 4px; color: #fff; }

/* Disabled buttons need to stay visible against the dark canvas */
button:disabled {
    opacity: 0.55 !important;
}

/* Streamlit native tweaks — tighten the default sidebar header */
section[data-testid="stSidebar"] .block-container {
    padding-top: 1.6rem;
}

/* Code blocks — brand them */
pre, code {
    background: var(--bg-soft) !important;
    color: var(--text-1) !important;
}

/* Expander caret + border refinement */
details {
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 8px;
}
details > summary { padding: 10px 14px !important; }
</style>
"""


_INJECTED_FLAG = "_axion_css_injected"


def inject_global_css() -> None:
    """Call once per page after `st.set_page_config`."""
    if st.session_state.get(_INJECTED_FLAG):
        return
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.session_state[_INJECTED_FLAG] = True


def render_banner(title: str, subtitle: str, *, tags: list[str] | None = None) -> None:
    """Render the gradient hero banner. Tags become small uppercase chips next to the title."""
    tags_html = ""
    if tags:
        tags_html = " ".join(f"<span class='axion-tag'>{t}</span>" for t in tags)
    st.markdown(
        f"""
        <div class='axion-banner'>
          <h1>{tags_html}{title}</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


_SeverityPill = Literal["info", "success", "warning", "error", "blocker", "neutral"]


def severity_pill(severity: str, label: str | None = None) -> str:
    """Return an HTML pill string for a severity; safe to embed via st.markdown(unsafe)."""
    cls_map = {
        "info": "pill-info",
        "success": "pill-success",
        "warning": "pill-warning",
        "error": "pill-error",
        "blocker": "pill-blocker",
        "neutral": "pill-neutral",
    }
    cls = cls_map.get(severity, "pill-neutral")
    text = label if label is not None else severity.upper()
    return f"<span class='pill {cls}'>{text}</span>"


def styled_error(message: str, *, title: str = "Something didn't load") -> None:
    """Render a friendly error callout — used when an API call fails. No stack traces."""
    st.markdown(
        f"""
        <div class='axion-error'>
          <div class='axion-error-title'>{title}</div>
          <div>{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_strip(items: list[tuple[str, str]]) -> None:
    """Render a horizontal metric strip from (label, value) pairs."""
    cells = "".join(
        f"<div class='metric-cell'><div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div></div>"
        for label, value in items
    )
    st.markdown(f"<div class='metric-strip'>{cells}</div>", unsafe_allow_html=True)


# Severity → traffic-light color (used for alignment / consistency-index displays).
def traffic_color(score: float, *, hi: float = 80.0, mid: float = 50.0) -> str:
    if score >= hi:
        return "var(--success)"
    if score >= mid:
        return "var(--warning)"
    return "var(--danger)"


SEVERITY_EMOJI = {"info": "🟢", "warning": "🟡", "error": "🔴", "blocker": "⛔"}
SEVERITY_RANK = {"blocker": 0, "error": 1, "warning": 2, "info": 3}
