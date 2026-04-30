"""Shared Streamlit styling — palette, banners, status pills, error callouts, layout helpers.

Every page calls `inject_global_css()` once after `st.set_page_config`. The CSS lives in
this module (not on disk) so the UI ships as a pure pip-installed package.

Brand: **Lumeo Campaign Studio**. Palette is the P11 refresh — layered surfaces,
calm electric-blue accent, mint positive accent. See ADR-009 for the rationale.

Public surface
--------------
- inject_global_css()             — idempotent CSS injection; call once per page
- top_header()                    — centered product wordmark, rendered above the banner
- render_banner(title, subtitle)  — gradient hero with kicker (overline) ABOVE the H1
- section_header(title, kicker)   — section heading row with optional right-action slot
- info_card(title, body)          — minimal card wrapper
- key_value_table(rows)           — structured table replacing raw JSON dumps
- empty_state(...)                — friendly empty-state card
- severity_pill(severity, label?) — pill HTML string
- styled_error(message, ...)      — friendly error callout (no stack traces)
- metric_strip(items)             — horizontal metric strip
- traffic_color(score, hi, mid)   — threshold → CSS color var
- scrub_override_prefix(text)     — strip `[override:*]` audit prefix at render time only
- scroll_to(anchor_id)            — JS smooth-scroll into view (Streamlit iframe-safe)
"""
from __future__ import annotations

import re
from typing import Iterable, Literal, Sequence

import streamlit as st


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

PRODUCT_NAME = "Lumeo"
PRODUCT_TAGLINE = "Campaign Studio"


# ---------------------------------------------------------------------------
# Global CSS — palette + typography + components
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
:root {
    /* Layered surfaces — page < panel < elevated */
    --bg-canvas:    #0B1220;
    --bg-panel:     #131C2E;
    --bg-elevated:  #1B2742;
    --bg-input:     #0F1828;

    --border-subtle: #1F2C46;
    --border-strong: #2C3C5C;

    --text-primary:   #ECF1F7;
    --text-secondary: #9FAEC4;
    --text-muted:     #6B7B96;
    --text-inverse:   #0B1220;

    --accent:       #4F8CFF;
    --accent-soft:  rgba(79, 140, 255, 0.14);
    --accent-2:     #6FE1C0;

    --success: #2BD68A;
    --warning: #F2B847;
    --danger:  #F26A6A;
    --info:    #6FB3F2;

    /* Backwards-compat aliases for code that still references the old token names. */
    --bg-deep:  var(--bg-canvas);
    --bg-soft:  var(--bg-elevated);
    --text-1:   var(--text-primary);
    --text-2:   var(--text-secondary);
    --border:   var(--border-subtle);
}

html, body, [class*="css"] {
    font-family: "Inter", "Segoe UI", -apple-system, system-ui, sans-serif;
}

/* Type rhythm */
h1 { font-size: 1.75rem; font-weight: 650; letter-spacing: -0.015em;
     line-height: 1.2; color: var(--text-primary) !important; margin-top: 0; }
h2 { font-size: 1.25rem; font-weight: 600; color: var(--text-primary) !important;
     letter-spacing: -0.01em; }
h3 { font-size: 1.05rem; font-weight: 600; color: var(--text-primary) !important; }
p, li, label, span { color: var(--text-primary); }
.lumeo-caption { color: var(--text-secondary); font-size: 0.82rem; }

/* ---------------------------- Top product header ---------------------------- */
.lumeo-top-header {
    display: flex; align-items: center; justify-content: center;
    gap: 12px;
    padding: 14px 0 10px 0;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border-subtle);
}
.lumeo-top-header .wordmark {
    display: inline-flex; align-items: center; gap: 10px;
    font-weight: 700; font-size: 1.25rem; color: var(--text-primary);
    letter-spacing: -0.02em;
}
.lumeo-top-header .wordmark .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
    box-shadow: 0 0 14px rgba(79, 140, 255, 0.45);
    flex: none;
}
.lumeo-top-header .wordmark .tagline {
    color: var(--text-secondary); font-weight: 500; font-size: 0.9rem;
    letter-spacing: 0;
}

/* ---------------------------- Hero banner ---------------------------------- */
.lumeo-banner {
    background: linear-gradient(120deg, #1B2742 0%, #131C2E 100%);
    border: 1px solid var(--border-subtle);
    border-top: 1px solid var(--accent);
    padding: 22px 26px 20px 26px;
    border-radius: 14px;
    margin: 8px 0 22px 0;
}
.lumeo-banner .lumeo-overline {
    color: var(--accent); font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin: 0 0 6px 0;
}
.lumeo-banner h1 {
    margin: 0 0 6px 0; color: var(--text-primary) !important;
    font-size: 1.6rem; font-weight: 650; letter-spacing: -0.015em;
}
.lumeo-banner p {
    margin: 0; color: var(--text-secondary);
    font-size: 0.94rem; line-height: 1.5; max-width: 880px;
}

/* Backwards-compat: existing pages may still use .axion-banner. Map to new style. */
.axion-banner {
    background: linear-gradient(120deg, #1B2742 0%, #131C2E 100%);
    border: 1px solid var(--border-subtle);
    border-top: 1px solid var(--accent);
    padding: 22px 26px;
    border-radius: 14px;
    margin: 8px 0 22px 0;
    color: var(--text-primary);
}
.axion-banner h1 {
    margin: 0 0 6px 0; color: var(--text-primary) !important;
    font-size: 1.6rem; font-weight: 650;
}
.axion-banner p {
    margin: 0; color: var(--text-secondary);
    font-size: 0.94rem; line-height: 1.5; max-width: 880px;
}

/* Phase / section overline chips (used by render_banner kicker AND section_header) */
.lumeo-overline, .axion-tag {
    display: inline-block;
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-right: 8px;
    vertical-align: middle;
}

/* ---------------------------- Section header ------------------------------ */
.lumeo-section {
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 18px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border-subtle);
}
.lumeo-section .lumeo-section-text { display: flex; flex-direction: column; }
.lumeo-section .lumeo-section-text .lumeo-overline { margin-bottom: 2px; }
.lumeo-section h2 { margin: 0; font-size: 1.15rem; }
.lumeo-section .lumeo-section-action { color: var(--text-secondary); font-size: 0.85rem; }

/* ---------------------------- Cards --------------------------------------- */
.lumeo-card, .axion-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 12px;
}
.lumeo-card h4, .axion-card h4 {
    margin: 0 0 6px 0; color: var(--text-primary); font-size: 1rem;
}
.lumeo-card .lumeo-card-body, .axion-card .lumeo-card-body {
    color: var(--text-secondary); font-size: 0.92rem; line-height: 1.5;
}

/* ---------------------------- Severity pills ------------------------------ */
.pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid transparent;
    line-height: 1.5;
}
.pill-info    { background: rgba(111,179,242,0.12); color: var(--info);    border-color: rgba(111,179,242,0.4); }
.pill-success { background: rgba(43,214,138,0.12);  color: var(--success); border-color: rgba(43,214,138,0.4); }
.pill-warning { background: rgba(242,184,71,0.14);  color: var(--warning); border-color: rgba(242,184,71,0.45); }
.pill-error   { background: rgba(242,106,106,0.14); color: var(--danger);  border-color: rgba(242,106,106,0.45); }
.pill-blocker { background: var(--danger); color: #fff; border-color: var(--danger); }
.pill-neutral { background: rgba(159,174,196,0.12); color: var(--text-secondary); border-color: rgba(159,174,196,0.3); }

/* ---------------------------- Metric strip -------------------------------- */
.metric-strip {
    display: flex; gap: 14px; flex-wrap: wrap;
    background: var(--bg-elevated);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 12px;
}
.metric-strip .metric-cell { min-width: 130px; }
.metric-strip .metric-label {
    color: var(--text-secondary); font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 2px;
}
.metric-strip .metric-value {
    color: var(--text-primary); font-size: 1.3rem; font-weight: 600;
}

/* ---------------------------- Error callout ------------------------------- */
.lumeo-error, .axion-error {
    background: rgba(242,106,106,0.08);
    border: 1px solid rgba(242,106,106,0.35);
    color: var(--danger);
    padding: 12px 16px;
    border-radius: 10px;
    margin: 10px 0;
    font-size: 0.88rem;
}
.lumeo-error .lumeo-error-title, .axion-error .axion-error-title {
    font-weight: 700; margin-bottom: 4px; color: #fff;
}
.lumeo-error details { margin-top: 6px; }
.lumeo-error details summary {
    cursor: pointer; color: var(--text-secondary); font-size: 0.8rem;
    list-style: none;
}

/* ---------------------------- Key/value table ----------------------------- */
.lumeo-kv {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 12px;
}
.lumeo-kv th, .lumeo-kv td {
    padding: 8px 12px;
    text-align: left;
    font-size: 0.88rem;
    border-bottom: 1px solid var(--border-subtle);
    vertical-align: top;
}
.lumeo-kv tr:last-child td { border-bottom: none; }
.lumeo-kv th {
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.72rem;
}
.lumeo-kv td.kv-field {
    color: var(--text-secondary);
    width: 30%;
}
.lumeo-kv td.kv-value { color: var(--text-primary); }
.lumeo-kv td.kv-status { width: 1%; white-space: nowrap; }

/* ---------------------------- Empty state --------------------------------- */
.lumeo-empty {
    background: var(--bg-panel);
    border: 1px dashed var(--border-strong);
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    margin: 12px 0;
}
.lumeo-empty .lumeo-empty-icon { font-size: 2.2rem; line-height: 1; margin-bottom: 8px; }
.lumeo-empty .lumeo-empty-title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.lumeo-empty .lumeo-empty-body  { color: var(--text-secondary); font-size: 0.92rem; margin-top: 4px; }

/* ---------------------------- Streamlit overrides ------------------------- */
section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
section[data-testid="stSidebarNav"] li a span {
    text-transform: none;
    font-weight: 500;
    letter-spacing: 0;
    font-size: 0.93rem;
}
section[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: var(--accent-soft);
    border-radius: 6px;
}
button:disabled { opacity: 0.55 !important; }

/* Code blocks */
pre, code {
    background: var(--bg-elevated) !important;
    color: var(--text-primary) !important;
    border-radius: 8px;
}

/* Expander frame */
details {
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    margin-bottom: 8px;
}
details > summary { padding: 10px 14px !important; }
</style>
"""


_INJECTED_FLAG = "_lumeo_css_injected"


def inject_global_css() -> None:
    """Idempotent CSS injection. Call once per page after `st.set_page_config`."""
    if st.session_state.get(_INJECTED_FLAG):
        return
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.session_state[_INJECTED_FLAG] = True


# ---------------------------------------------------------------------------
# Top header — centered product wordmark
# ---------------------------------------------------------------------------


def top_header(*, subtitle: str | None = None) -> None:
    """Centered product wordmark + tagline. Render once per page, above the banner.

    Subtitle defaults to the canonical product tagline. Pass a per-page subtitle to
    customize the rightmost text (kept short — the page banner carries the page title)."""
    sub = subtitle if subtitle is not None else PRODUCT_TAGLINE
    sub_html = (
        f"<span class='tagline'>{_safe_text(sub)}</span>" if sub else ""
    )
    st.markdown(
        "<div class='lumeo-top-header'>"
        "<div class='wordmark'>"
        "<span class='dot'></span>"
        f"<span>{PRODUCT_NAME}</span>"
        f"{sub_html}"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Banner — kicker (overline) ABOVE the H1, fixing the W1 liveW1 / P8 regressionEval
# / P8 traceObservability concatenation bug. Tags → kicker line.
# ---------------------------------------------------------------------------


def render_banner(
    title: str,
    subtitle: str,
    *,
    tags: Sequence[str] | None = None,
    kicker: str | None = None,
) -> None:
    """Hero banner. The previous behavior concatenated tags inline with the H1;
    this version places `kicker` (or, for backwards compat, joined `tags`) on a separate
    overline row ABOVE the title."""
    overline_text = ""
    if kicker:
        overline_text = kicker
    elif tags:
        overline_text = " · ".join(t for t in tags if t)
    overline_html = (
        f"<div class='lumeo-overline'>{_safe_text(overline_text)}</div>"
        if overline_text
        else ""
    )
    st.markdown(
        "<div class='lumeo-banner'>"
        f"{overline_html}"
        f"<h1>{_safe_text(title)}</h1>"
        f"<p>{_safe_text(subtitle)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Section header
# ---------------------------------------------------------------------------


def section_header(
    title: str,
    *,
    kicker: str | None = None,
    action: str | None = None,
) -> None:
    """Render a section heading with optional kicker overline and right-aligned action text."""
    kicker_html = (
        f"<div class='lumeo-overline'>{_safe_text(kicker)}</div>" if kicker else ""
    )
    action_html = (
        f"<div class='lumeo-section-action'>{_safe_text(action)}</div>" if action else ""
    )
    st.markdown(
        "<div class='lumeo-section'>"
        "<div class='lumeo-section-text'>"
        f"{kicker_html}"
        f"<h2>{_safe_text(title)}</h2>"
        "</div>"
        f"{action_html}"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Info card
# ---------------------------------------------------------------------------


def info_card(title: str, body: str) -> None:
    """Minimal card wrapper. Use sparingly — prefer `key_value_table` for structured data."""
    st.markdown(
        "<div class='lumeo-card'>"
        f"<h4>{_safe_text(title)}</h4>"
        f"<div class='lumeo-card-body'>{body}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Key/value table — replaces raw JSON dumps
# ---------------------------------------------------------------------------


_StatusToken = Literal["confirmed", "inferred", "gap", "missing", "neutral"]


_STATUS_PILL: dict[str, str] = {
    "confirmed": "success",
    "inferred": "info",
    "gap": "warning",
    "missing": "error",
    "neutral": "neutral",
}


def _status_cell(status: str | None) -> str:
    if not status:
        return ""
    pill = _STATUS_PILL.get(status.lower(), "neutral")
    return severity_pill(pill, status.upper())


def key_value_table(
    rows: Iterable[tuple],
    *,
    columns: tuple[str, str, str] = ("Field", "Value", "Status"),
    status_col: bool = True,
) -> None:
    """Render a structured table from `[(field, value, status?)]` rows.

    Replaces every `st.json(...)` dump in the user surface. The status column is
    optional; when omitted, `rows` is `[(field, value)]`."""
    rows_list = list(rows)
    head_cells = (
        f"<th>{columns[0]}</th><th>{columns[1]}</th><th>{columns[2]}</th>"
        if status_col
        else f"<th>{columns[0]}</th><th>{columns[1]}</th>"
    )
    body_rows: list[str] = []
    for r in rows_list:
        if status_col:
            field, value, status = (r + (None,))[:3] if len(r) == 2 else r[:3]
        else:
            field, value = r[:2]
            status = None
        cells = (
            f"<td class='kv-field'>{_safe_text(str(field))}</td>"
            f"<td class='kv-value'>{value if isinstance(value, str) else _safe_text(str(value))}</td>"
        )
        if status_col:
            cells += f"<td class='kv-status'>{_status_cell(status)}</td>"
        body_rows.append(f"<tr>{cells}</tr>")

    st.markdown(
        "<table class='lumeo-kv'>"
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def empty_state(
    icon: str,
    title: str,
    body: str = "",
    *,
    action_label: str | None = None,
    action_callback=None,
) -> None:
    """Friendly empty-state card. `action_callback` runs on button click; pass `None`
    when the page already provides the action through other UI."""
    st.markdown(
        "<div class='lumeo-empty'>"
        f"<div class='lumeo-empty-icon'>{_safe_text(icon)}</div>"
        f"<div class='lumeo-empty-title'>{_safe_text(title)}</div>"
        f"<div class='lumeo-empty-body'>{_safe_text(body)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if action_label and action_callback is not None:
        if st.button(action_label, key=f"_empty_state_{title}"):
            action_callback()


# ---------------------------------------------------------------------------
# Severity pill — single source of truth for severity rendering
# ---------------------------------------------------------------------------


_SeverityPill = Literal["info", "success", "warning", "error", "blocker", "neutral"]


def severity_pill(severity: str, label: str | None = None) -> str:
    """Return an HTML pill string. Safe to embed via `st.markdown(unsafe_allow_html=True)`."""
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
    return f"<span class='pill {cls}'>{_safe_text(text)}</span>"


# ---------------------------------------------------------------------------
# Friendly error callout — judges must NEVER see a raw stack trace
# ---------------------------------------------------------------------------


def styled_error(
    message: str,
    *,
    title: str = "Something didn't load",
    details: str | None = None,
) -> None:
    """Render a friendly error callout. `details` is hidden inside a `<details>` block
    for power users; keep the headline message human."""
    details_html = ""
    if details:
        details_html = (
            "<details><summary>Show technical details</summary>"
            f"<pre style='margin-top:8px; max-height:240px; overflow:auto'>"
            f"{_safe_text(details)}</pre></details>"
        )
    st.markdown(
        "<div class='lumeo-error'>"
        f"<div class='lumeo-error-title'>{_safe_text(title)}</div>"
        f"<div>{message}</div>"
        f"{details_html}"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Metric strip
# ---------------------------------------------------------------------------


def metric_strip(items: list[tuple[str, str]]) -> None:
    """Horizontal strip of (label, value) tiles."""
    cells = "".join(
        f"<div class='metric-cell'><div class='metric-label'>{_safe_text(label)}</div>"
        f"<div class='metric-value'>{_safe_text(value)}</div></div>"
        for label, value in items
    )
    st.markdown(f"<div class='metric-strip'>{cells}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Traffic-light color helper
# ---------------------------------------------------------------------------


def traffic_color(score: float, *, hi: float = 80.0, mid: float = 50.0) -> str:
    if score >= hi:
        return "var(--success)"
    if score >= mid:
        return "var(--warning)"
    return "var(--danger)"


# ---------------------------------------------------------------------------
# Override-prefix scrubber — display only; storage keeps the audit prefix
# ---------------------------------------------------------------------------


_OVERRIDE_PREFIX_RE = re.compile(r"^\[override:[^\]]+\]\s*")


def scrub_override_prefix(text: str) -> str:
    """Strip the `[override:field.path]` audit prefix from a string for DISPLAY ONLY.

    The prefix is intentionally written into `constraints.mandatory_inclusions` by
    `apply_overrides_to_brief` (ADR-008) so the audit trail is preserved. Only the
    rendered surface should hide it. Never write the scrubbed form back to storage.
    """
    if not text:
        return text
    return _OVERRIDE_PREFIX_RE.sub("", text)


# ---------------------------------------------------------------------------
# Smooth scroll-into-view — Streamlit-iframe-safe JS
# ---------------------------------------------------------------------------


def scroll_to(anchor_id: str) -> None:
    """Smooth-scroll the parent document to the element with `id={anchor_id}`.

    Streamlit's iframe sandbox is same-origin, so `window.parent.document` is
    addressable. If the JS path is blocked in some browsers, page authors can still
    rely on a plain markdown anchor link (`[↑](#{anchor_id})`) as a fallback.
    """
    try:
        from streamlit.components.v1 import html as _html_component
    except Exception:  # pragma: no cover — streamlit always ships this in 1.35+
        return
    _html_component(
        f"""
        <script>
          (function() {{
            try {{
              var doc = window.parent.document;
              var el = doc.getElementById({anchor_id!r});
              if (el) {{
                el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
              }}
            }} catch (e) {{ /* iframe blocked — caller should fall back to anchor links */ }}
          }})();
        </script>
        """,
        height=0,
    )


# ---------------------------------------------------------------------------
# Constants used by other modules
# ---------------------------------------------------------------------------


SEVERITY_EMOJI = {"info": "🟢", "warning": "🟡", "error": "🔴", "blocker": "⛔"}
SEVERITY_RANK = {"blocker": 0, "error": 1, "warning": 2, "info": 3}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_HTML_ESCAPE_TABLE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
}


def _safe_text(text: str) -> str:
    """Escape HTML control chars in text destined for rendered markdown.

    We deliberately do NOT escape quotes — title attributes are not rendered through
    this helper. Strings that legitimately contain `<` / `>` / `&` are kept readable.
    """
    if not text:
        return ""
    out = str(text)
    for c, repl in _HTML_ESCAPE_TABLE.items():
        out = out.replace(c, repl)
    return out
