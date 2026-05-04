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
    /* Light, production palette — Lumeo Campaign Studio (P11 Iteration 2).
       Layered surfaces: canvas (page) < elevated (cards) < panel (white inset).
       Indigo accent on a near-white canvas; high-contrast text for readability. */
    --bg-canvas:    #F6F7FB;   /* page background */
    --bg-panel:     #FFFFFF;   /* card / panel surface */
    --bg-elevated:  #EEF1F7;   /* hover, table headers, callouts */
    --bg-input:     #FFFFFF;

    --border-subtle: #E2E6EF;
    --border-strong: #C9D1DD;

    --text-primary:   #0F172A;  /* slate-900 */
    --text-secondary: #475569;  /* slate-600 */
    --text-muted:     #94A3B8;  /* slate-400 */
    --text-inverse:   #FFFFFF;

    --accent:       #4F46E5;   /* indigo-600 */
    --accent-hover: #4338CA;   /* indigo-700 */
    --accent-soft:  rgba(79, 70, 229, 0.10);
    --accent-2:     #0EA5E9;   /* sky-500, secondary highlight */

    --success: #16A34A;
    --warning: #CA8A04;
    --danger:  #DC2626;
    --info:    #0284C7;

    /* Backwards-compat aliases for code that still references the old token names. */
    --bg-deep:  var(--bg-canvas);
    --bg-soft:  var(--bg-elevated);
    --text-1:   var(--text-primary);
    --text-2:   var(--text-secondary);
    --border:   var(--border-subtle);
}

/* CSS-VERSION: 2026-05-04-v13 — to verify this stylesheet shipped, open DevTools
   (F12) → Elements → Ctrl+F → search "CSS-VERSION". View Source will NOT show it
   because Streamlit injects styles via JS at runtime — only DevTools sees the
   live DOM. If the version string in DevTools is stale, restart Streamlit:
   `rm -rf ui/__pycache__ ui/pages/__pycache__ && streamlit cache clear &&
   streamlit run ui/Home.py`. */

/* App-wide background swap — Streamlit's default light background still has subtle gray
   tones; force our canvas color so panels read clearly against it. */
[data-testid="stAppViewContainer"], .stApp { background: var(--bg-canvas); }

/* The Streamlit-native top toolbar is replaced by our global header. `display: none`
   removes it from layout entirely so it claims 0 vertical space — `visibility: hidden`
   used to leave its layout slot intact, producing the ~75px gap users saw between
   the dark header and the page banner. */
[data-testid="stHeader"],
[data-testid="stToolbar"],
header[data-testid="stHeader"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
}

/* The dark global header is `position: fixed` with `height: 64px` covering the top
   of the viewport. We don't push the entire app shell down (that broke main's
   ability to auto-expand when the sidebar collapses). Instead:
     - Sidebar gets `margin-top: 64px` (further down) so it starts below header.
     - Main column gets `padding-top: 64px` on its block-container so its content
       starts below the header. This is set in the `.block-container` rule below.
   This way main's `margin-left` stays controlled by Streamlit's collapse logic
   and the sidebar collapse + main expansion just works. */

/* Streamlit's main column has its own padding/max-width. Force the workflow surface
   to the full available width and minimal padding so the content sits close to the
   sidebar edge instead of floating in the middle of a half-empty canvas.

   IMPORTANT: every selector here must be SCOPED TO MAIN ONLY — the previous
   iteration used `[data-testid="stAppViewContainer"] .block-container` which also
   matched the SIDEBAR's inner `.block-container` (the sidebar is a descendant of
   `stAppViewContainer`), forcing it to width: 100% / padding: 0 / margin: 0 and
   breaking the sidebar's internal layout. We target only the main-column test-ids
   here. The sidebar's own `.block-container` is styled separately further down. */
.main, [data-testid="stMain"], [data-testid="stAppViewMain"] {
    padding: 0 !important;
}
.main > .block-container,
[data-testid="stMain"] > .block-container,
[data-testid="stAppViewMain"] > .block-container,
section[data-testid="stMain"] > div > .block-container {
    max-width: 100% !important;
    width: 100% !important;
    /* 64px header clearance + 1rem breathing room. */
    padding-top: calc(64px + 1rem) !important;
    padding-bottom: 2rem !important;
    padding-left: 1.4rem !important;
    padding-right: 1.6rem !important;
    margin: 0 !important;
}

/* --------------------- Global header (full-width dark bar) --------------------- */
.lumeo-global-header {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 64px;
    background: linear-gradient(90deg, #0B1220 0%, #131C2E 50%, #0B1220 100%);
    border-bottom: 1px solid rgba(79, 70, 229, 0.45);
    box-shadow: 0 2px 14px rgba(0, 0, 0, 0.18), inset 0 -2px 0 0 rgba(79, 70, 229, 0.25);
    z-index: 999;
    display: flex; align-items: center; justify-content: center;
}
.lumeo-global-header-inner {
    display: inline-flex; align-items: center; gap: 14px;
    color: #FFFFFF;
    font-size: 1.45rem; font-weight: 700;
    letter-spacing: -0.02em;
    font-family: "Inter", "Segoe UI", -apple-system, system-ui, sans-serif;
}
.lumeo-global-header-inner .gh-dot {
    width: 14px; height: 14px; border-radius: 50%;
    background: linear-gradient(135deg, #4F46E5 0%, #0EA5E9 100%);
    box-shadow: 0 0 0 5px rgba(79, 70, 229, 0.18);
    flex: none;
}
/* Both halves of the wordmark inherit the .lumeo-global-header-inner typography
   (1.45rem / 700 / -0.02em letter-spacing) so "Lumeo | Campaign Studio" reads as
   one continuous title. The pipe divider is rendered as plain inline text with a
   muted color so it visually separates without competing with the brand. */
.lumeo-global-header-inner .gh-name {
    color: #FFFFFF;
    font: inherit;
}
.lumeo-global-header-inner .gh-divider {
    color: rgba(255, 255, 255, 0.32);
    font: inherit;
    font-weight: 300;
    margin: 0 2px;
}
.lumeo-global-header-inner .gh-tag {
    color: #FFFFFF;
    font: inherit;
}

/* --------------------- Sidebar — narrow + clean nav --------------------- */
section[data-testid="stSidebar"] {
    background: var(--bg-panel);
    border-right: 1px solid var(--border-subtle);
    width: 184px !important;
    min-width: 184px !important;
}
section[data-testid="stSidebar"] > div:first-child { width: 184px !important; }
section[data-testid="stSidebar"] .block-container { padding: 1rem 0.85rem !important; }

/* Sidebar collapse arrows — push them physically below the dark header.

   Strategy: the dark header is `position: fixed; top:0; height:64px; z-index:999`.
   The sidebar element itself starts at top:0 (Streamlit default), which puts its
   top region (where the "<<" close arrow lives) directly behind the header.

   Fix: `margin-top: 64px` on the sidebar element pushes the WHOLE sidebar down
   by 64px so it begins at the header's bottom edge. The close arrow now sits at
   y ≈ 64 + small-padding ≈ 70-80, immediately below the dark band. We also clamp
   the sidebar's height to `calc(100vh - 64px)` so it doesn't overflow the bottom
   of the viewport.

   When the user clicks "<<", Streamlit slides the sidebar off-screen (this works
   natively — we don't interfere). Streamlit then renders a floating ">>" reopen
   toggle which defaults to `top:0.5rem;left:0.5rem;` (behind our header). We
   override its position to `top:76px;left:14px;` and bump `z-index` above the
   header's 999 so it sits ON TOP of the header bar and is clickable. We also
   force display/visibility/opacity/pointer-events to ensure no inherited rule
   accidentally hides it. */
section[data-testid="stSidebar"] {
    margin-top: 64px !important;
    height: calc(100vh - 64px) !important;
}

[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    position: fixed !important;
    top: 76px !important;
    left: 14px !important;
    z-index: 1001 !important;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
}

/* When the sidebar is collapsed, Streamlit slides it off-screen via transform
   or margin-left, and the main content area auto-expands to fill. Make sure
   nothing in our CSS prevents that auto-expansion: do NOT pin main's margin-left
   to 184px or any fixed value. Streamlit handles the responsive width natively
   — our `.block-container` width:100% rule above lets it fill whatever space
   Streamlit allocates. */

/* Sidebar text colors — target text-bearing elements only. The previous broad `*`
   selector cascaded into SVG icons and Streamlit-internal widgets, which use the
   computed `color` value as their stroke/fill in some cases — overriding to
   slate-900 then made certain controls invisible against the panel background. */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--text-primary);
}

/* Defensive hide for the legacy `_fallback` page row in case any cached Streamlit
   build still discovers underscore-prefixed pages. The file itself has been removed
   from `ui/pages/`, but if the user's session was opened against the prior build
   the link may briefly persist until full restart. Targeted by href substring + by
   text content so version drift in DOM structure doesn't invalidate the rule.

   We DO NOT hide the first nav row anymore — the entry script was renamed from
   `app.py` to `Home.py`, so the first row now reads "Home" which is a real,
   valid landing-page navigation entry. */
section[data-testid="stSidebarNav"] a[href*="fallback"],
section[data-testid="stSidebarNav"] a[href*="_fallback"],
section[data-testid="stSidebarNav"] a[href*="/app"][href$="/app"] {
    display: none !important;
}
/* :has() requires Chrome 105+ / Safari 15.4+ / Firefox 121+ — fine for the target
   browsers (Chrome / Edge / Safari). Hides the entire <li>/<div> wrapping the
   anchor so we don't end up with empty list rows. */
section[data-testid="stSidebarNav"] li:has(a[href*="fallback"]),
section[data-testid="stSidebarNav"] li:has(a[href*="_fallback"]) {
    display: none !important;
}

section[data-testid="stSidebarNav"] li a {
    border-radius: 8px;
    padding: 7px 10px !important;
    margin: 1px 0;
    transition: background 0.15s ease;
}
section[data-testid="stSidebarNav"] li a:hover { background: var(--bg-elevated) !important; }
section[data-testid="stSidebarNav"] li a span {
    text-transform: none !important;
    font-weight: 500;
    letter-spacing: 0;
    font-size: 0.93rem;
}
section[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: var(--accent-soft) !important;
}
section[data-testid="stSidebarNav"] li a[aria-current="page"] span {
    color: var(--accent) !important;
    font-weight: 600;
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

/* ---------------------------- Step rail with arrows ---------------------- */
.lumeo-step-rail {
    display: flex; align-items: center; flex-wrap: wrap;
    gap: 4px; margin: 14px 0 22px 0;
}
.lumeo-step-rail .step-pill {
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 0.92rem;
    font-weight: 600;
    border: 1px solid var(--border-subtle);
    background: var(--bg-panel);
    color: var(--text-secondary);
    flex: 1 1 0;
    text-align: center;
    transition: transform 0.12s ease;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.lumeo-step-rail .step-pill.done {
    background: rgba(22, 163, 74, 0.10);
    color: var(--success);
    border-color: rgba(22, 163, 74, 0.32);
}
.lumeo-step-rail .step-pill.current {
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%);
    color: #FFFFFF;
    border-color: var(--accent);
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.30);
}
.lumeo-step-rail .step-pill.pending {
    background: var(--bg-panel);
    color: var(--text-muted);
    border-color: var(--border-subtle);
}
.lumeo-step-rail .step-arrow {
    color: var(--text-muted); font-size: 1.15rem; font-weight: 700;
    flex: 0 0 auto; padding: 0 2px;
    user-select: none;
}

/* ---------------------------- Compact score legend ---------------------- */
.lumeo-legend-strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    margin: 0;
    padding: 14px 18px;
    background: var(--bg-elevated);
    border-top: 1px solid var(--border-subtle);
    border-radius: 0 0 14px 14px;
}
.lumeo-legend-item {
    display: flex; flex-direction: column; gap: 6px;
    padding: 0 18px;
    border-right: 1px solid var(--border-subtle);
    min-height: 60px;
    justify-content: center;
}
.lumeo-legend-item:last-child {
    border-right: none;
    padding-right: 18px;
}
/* Uniform padding on every column so the three legend tiles read as evenly
   divided (the prior `:first-child { padding-left: 0 }` rule made the leftmost
   column visibly narrower than the other two). */
.lumeo-legend-item:first-child { padding-left: 18px; }
.lumeo-legend-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    align-self: flex-start;
}
.lumeo-legend-chip.legend-blue   { background: rgba(59,130,246,0.12);  color: #2563EB; border: 1px solid rgba(59,130,246,0.32); }
.lumeo-legend-chip.legend-mint   { background: rgba(20,184,166,0.12);  color: #0F766E; border: 1px solid rgba(20,184,166,0.32); }
.lumeo-legend-chip.legend-violet { background: rgba(139,92,246,0.12);  color: #7C3AED; border: 1px solid rgba(139,92,246,0.32); }
.lumeo-legend-text {
    color: var(--text-secondary);
    font-size: 0.86rem;
    line-height: 1.5;
}

/* When the legend strip is appended to a banner, eliminate the gap between them. */
.lumeo-banner.banner-with-legend {
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    margin-bottom: 0;
}
.lumeo-banner.banner-with-legend + .lumeo-legend-strip {
    border: 1px solid var(--border-subtle);
    border-top: none;
    margin-bottom: 22px;
}

/* ---------------------------- Hero banner ---------------------------------- */
.lumeo-banner {
    background: linear-gradient(135deg, #FFFFFF 0%, #F1F4FB 100%);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--accent);
    padding: 22px 26px 20px 26px;
    border-radius: 14px;
    margin: 8px 0 22px 0;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.lumeo-banner .lumeo-overline {
    color: var(--accent); font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.10em;
    margin: 0 0 6px 0;
}
.lumeo-banner h1 {
    margin: 0 0 6px 0; color: var(--text-primary) !important;
    font-size: 1.6rem; font-weight: 700; letter-spacing: -0.015em;
}
.lumeo-banner p {
    margin: 0; color: var(--text-secondary);
    font-size: 0.94rem; line-height: 1.55; max-width: 880px;
}

/* Backwards-compat: existing pages may still use .axion-banner. Map to new style. */
.axion-banner {
    background: linear-gradient(135deg, #FFFFFF 0%, #F1F4FB 100%);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--accent);
    padding: 22px 26px; border-radius: 14px;
    margin: 8px 0 22px 0; color: var(--text-primary);
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.axion-banner h1 {
    margin: 0 0 6px 0; color: var(--text-primary) !important;
    font-size: 1.6rem; font-weight: 700;
}
.axion-banner p {
    margin: 0; color: var(--text-secondary);
    font-size: 0.94rem; line-height: 1.55; max-width: 880px;
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
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.lumeo-card:hover, .axion-card:hover {
    border-color: var(--border-strong);
}
.lumeo-card h4, .axion-card h4 {
    margin: 0 0 6px 0; color: var(--text-primary); font-size: 1rem; font-weight: 600;
}
.lumeo-card .lumeo-card-body, .axion-card .lumeo-card-body {
    color: var(--text-secondary); font-size: 0.92rem; line-height: 1.55;
}

/* Sanitized copy preview block — used inline on Plan from Brief. Card-like surface
   with a header bar (channel icon + Copy button) so the copy doesn't read as plain
   text. The previous indigo left strip was removed in favour of the header bar +
   line-aware formatting on labeled lines (Subject:, Preheader:, Touch N:, For X:). */
.lumeo-copy-frame {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    margin: 10px 0;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    overflow: hidden;
}
.lumeo-copy-frame-label {
    background: linear-gradient(180deg, #F8FAFF 0%, #EEF2FF 100%);
    color: var(--accent);
    font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 6px 14px;
    border-bottom: 1px solid var(--border-subtle);
}
.lumeo-copy-pre {
    background: var(--bg-panel);
    border: none !important;
    border-radius: 0 !important;
    padding: 14px 16px;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 260px;
    overflow-y: auto;
    font-size: 0.88rem;
    color: var(--text-primary);
    font-family: "SF Mono", Menlo, Consolas, monospace;
    line-height: 1.55;
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
.pill-info    { background: rgba(2,132,199,0.10);  color: var(--info);    border-color: rgba(2,132,199,0.35); }
.pill-success { background: rgba(22,163,74,0.10);   color: var(--success); border-color: rgba(22,163,74,0.35); }
.pill-warning { background: rgba(202,138,4,0.10);   color: var(--warning); border-color: rgba(202,138,4,0.35); }
.pill-error   { background: rgba(220,38,38,0.10);   color: var(--danger);  border-color: rgba(220,38,38,0.35); }
.pill-blocker { background: var(--danger); color: #fff; border-color: var(--danger); }
.pill-neutral { background: rgba(71,85,105,0.08);   color: var(--text-secondary); border-color: rgba(71,85,105,0.25); }

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
    background: rgba(220, 38, 38, 0.06);
    border: 1px solid rgba(220, 38, 38, 0.30);
    color: var(--danger);
    padding: 12px 16px;
    border-radius: 10px;
    margin: 10px 0;
    font-size: 0.9rem;
}
.lumeo-error .lumeo-error-title, .axion-error .axion-error-title {
    font-weight: 700; margin-bottom: 4px; color: var(--danger);
}

/* ---------------------------- Score legend cards -------------------------- */
.score-legend-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
    margin: 12px 0 22px 0;
}
.score-legend-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 14px 16px 12px 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    border-top: 3px solid var(--accent);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.score-legend-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}
.score-legend-blue   { border-top-color: #3B82F6; background: linear-gradient(180deg, rgba(59,130,246,0.04) 0%, var(--bg-panel) 60%); }
.score-legend-mint   { border-top-color: #14B8A6; background: linear-gradient(180deg, rgba(20,184,166,0.05) 0%, var(--bg-panel) 60%); }
.score-legend-violet { border-top-color: #8B5CF6; background: linear-gradient(180deg, rgba(139,92,246,0.05) 0%, var(--bg-panel) 60%); }
.score-legend-icon { font-size: 1.25rem; margin-bottom: 4px; }
.score-legend-title {
    font-weight: 700; font-size: 0.95rem; color: var(--text-primary);
    margin-bottom: 6px; letter-spacing: -0.01em;
}
.score-legend-desc {
    color: var(--text-secondary); font-size: 0.85rem; line-height: 1.5;
    margin-bottom: 8px;
}
.score-legend-hint {
    color: var(--text-muted); font-size: 0.74rem;
    text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
}

/* ---------------------------- Asset builder cards ------------------------ */
/* The asset slot used to render as a full white card behind the inputs; the
   user feedback is that the boxed look competes with the input fields below.
   Slot grouping is now achieved purely through the top-of-slot pill + a thin
   bottom divider — the frame itself is transparent. */
.asset-card-frame {
    background: transparent;
    border: none;
    border-bottom: 1px dashed var(--border-subtle);
    border-radius: 0;
    padding: 4px 0 18px 0;
    margin-bottom: 14px;
    box-shadow: none;
}
.asset-card-frame:last-child { border-bottom: none; }
/* Legacy header strip — kept as an inline-flex container so old callsites still
   render, but no longer renders as a full-width band. */
.asset-card-frame .asset-card-header {
    display: inline-flex; align-items: center;
    margin-bottom: 8px;
}
/* New compact pill used as the asset slot label. Sits inline at the top of the
   asset card frame; clearly differentiated from the white input fields below. */
.asset-card-frame .asset-card-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.70rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    border: 1px solid rgba(79, 70, 229, 0.22);
    margin-bottom: 10px;
    line-height: 1.6;
}
/* Backwards compat — old `.asset-card-label` callsites keep working but adopt
   the new pill look. */
.asset-card-frame .asset-card-label {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.70rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    border: 1px solid rgba(79, 70, 229, 0.22);
    line-height: 1.6;
}

/* ---------------------------- Landing hero -------------------------------- */
.lumeo-hero {
    margin: 8px 0 28px 0;
    padding: 56px 40px 60px 40px;
    border-radius: 20px;
    background:
        radial-gradient(ellipse at 20% 0%, rgba(79,70,229,0.18) 0%, rgba(79,70,229,0.0) 55%),
        radial-gradient(ellipse at 100% 100%, rgba(14,165,233,0.16) 0%, rgba(14,165,233,0.0) 55%),
        linear-gradient(135deg, #EEF2FF 0%, #F0FDFA 100%);
    border: 1px solid rgba(79, 70, 229, 0.16);
    box-shadow: 0 6px 28px rgba(15, 23, 42, 0.06);
    text-align: center;
    position: relative; overflow: hidden;
}
.lumeo-hero::before {
    content: "";
    position: absolute; inset: 0;
    background:
        radial-gradient(circle at 80% 20%, rgba(139,92,246,0.10) 0%, rgba(139,92,246,0.0) 30%),
        radial-gradient(circle at 15% 85%, rgba(20,184,166,0.10) 0%, rgba(20,184,166,0.0) 35%);
    pointer-events: none;
}
.lumeo-hero h1 {
    font-size: 2.6rem !important; font-weight: 800; letter-spacing: -0.03em;
    margin: 0 0 14px 0;
    background: linear-gradient(135deg, #4F46E5 0%, #8B5CF6 60%, #0EA5E9 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    position: relative;
}
.lumeo-hero p {
    font-size: 1.05rem; color: var(--text-secondary);
    max-width: 680px; margin: 0 auto; line-height: 1.6;
    position: relative;
}
.lumeo-hero .hero-eyebrow {
    display: inline-block;
    color: var(--accent); font-size: 0.74rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.14em;
    background: rgba(79,70,229,0.10);
    padding: 5px 12px; border-radius: 999px;
    margin-bottom: 16px; position: relative;
}

/* Workflow card grid — equal-height, hover-lift, gradient top edge per card. */
.workflow-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-top: 20px;
}
.workflow-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 22px 22px 18px 22px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    display: flex; flex-direction: column;
    min-height: 240px;
    /* `height: 100%` lets cards in the same row grow to match the tallest in
       the row when wrapped in a flex/grid container that stretches. */
    height: 100%;
    position: relative; overflow: hidden;
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}
/* Ensure the workflow grid flex-stretches its children so the cards on the
   same row equalize on the tallest one. */
.workflow-grid > * { display: flex; }
.workflow-grid > * > .workflow-card { width: 100%; }
/* Anchor wrapper for clickable workflow cards on the landing page. */
a.workflow-card-link {
    text-decoration: none !important;
    color: inherit !important;
    display: block;
    height: 100%;
}
a.workflow-card-link:hover .workflow-card,
a.workflow-card-link:focus .workflow-card {
    transform: translateY(-4px);
    box-shadow: 0 12px 28px rgba(79, 70, 229, 0.18);
    border-color: rgba(79, 70, 229, 0.40);
}
a.workflow-card-link:active .workflow-card {
    transform: translateY(-1px);
}
.workflow-card::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--accent) 0%, var(--accent-2) 100%);
}
.workflow-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10);
    border-color: rgba(79, 70, 229, 0.32);
}
.workflow-card .workflow-icon {
    font-size: 1.6rem; margin-bottom: 10px;
}
.workflow-card h3 {
    margin: 0 0 8px 0; font-size: 1.1rem; font-weight: 650;
    color: var(--text-primary);
}
.workflow-card p {
    color: var(--text-secondary); font-size: 0.92rem; line-height: 1.55;
    margin: 0; flex-grow: 1;
}
.workflow-card .workflow-spacer { flex-grow: 1; }

/* Soft info / warning callouts — used for inline guidance like the score legend. */
.lumeo-callout {
    background: var(--accent-soft);
    border: 1px solid rgba(79, 70, 229, 0.25);
    color: var(--text-primary);
    padding: 12px 16px;
    border-radius: 10px;
    margin: 8px 0 14px 0;
    font-size: 0.9rem; line-height: 1.55;
}
.lumeo-callout strong { color: var(--text-primary); }
.lumeo-callout-warning {
    background: rgba(202, 138, 4, 0.08);
    border-color: rgba(202, 138, 4, 0.30);
}
.lumeo-callout-success {
    background: rgba(22, 163, 74, 0.08);
    border-color: rgba(22, 163, 74, 0.30);
}

/* ---------------------------- Gap cards ----------------------------------- */
.gap-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--text-muted);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.gap-card.gap-hard { border-left-color: var(--danger); background: linear-gradient(90deg, rgba(220,38,38,0.04) 0%, var(--bg-panel) 30%); }
.gap-card.gap-soft { border-left-color: var(--warning); background: linear-gradient(90deg, rgba(202,138,4,0.04) 0%, var(--bg-panel) 30%); }
.gap-card .gap-card-head {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    flex-wrap: wrap;
}
.gap-card .gap-card-field {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    color: var(--text-secondary); font-size: 0.82rem;
}
.gap-card .gap-card-desc {
    color: var(--text-primary); font-size: 0.92rem;
    line-height: 1.55; margin: 4px 0 6px 0;
}
.gap-card .gap-card-meta {
    color: var(--text-muted); font-size: 0.78rem;
}
.gap-card .gap-card-questions {
    margin-top: 8px; padding-top: 8px;
    border-top: 1px dashed var(--border-subtle);
}
.gap-card .gap-card-questions-title {
    color: var(--text-secondary); font-size: 0.74rem;
    text-transform: uppercase; letter-spacing: 0.06em;
    font-weight: 600; margin-bottom: 4px;
}
.gap-card .gap-card-questions ul {
    margin: 0; padding-left: 18px; color: var(--text-secondary); font-size: 0.86rem;
}

/* Collapsible gap / finding cards — native <details>/<summary>.

   The wrapping <details> wears the same `gap-card gap-hard|gap-soft` (or
   `finding-card finding-blocker|finding-error|...`) classes as the static
   block, so the severity left-edge color is preserved without rewriting the
   palette rules. The default disclosure triangle is hidden; we add a rotating
   chevron via ::after for a polished, on-brand toggle. */
details.gap-card,
details.finding-card {
    background: var(--bg-panel);
    margin-bottom: 10px;
    padding: 0;
}
details.gap-card[open],
details.finding-card[open] {
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
}
details.gap-card > summary,
details.finding-card > summary {
    list-style: none;
    cursor: pointer;
    padding: 12px 16px !important;
    user-select: none;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    color: var(--text-primary) !important;
}
details.gap-card > summary::-webkit-details-marker,
details.finding-card > summary::-webkit-details-marker {
    display: none;
}
details.gap-card > summary::after,
details.finding-card > summary::after {
    content: "\\203A"; /* › */
    margin-left: auto;
    color: var(--text-muted);
    font-size: 1.4rem;
    line-height: 0.6;
    transition: transform 0.18s ease;
    transform: rotate(90deg);
    font-weight: 700;
}
details.gap-card[open] > summary::after,
details.finding-card[open] > summary::after {
    transform: rotate(-90deg);
    color: var(--accent);
}
details.gap-card > summary:hover,
details.finding-card > summary:hover {
    background: var(--bg-elevated);
}
details.gap-card > .gap-card-body,
details.finding-card > .finding-card-body {
    padding: 4px 16px 14px 16px;
    border-top: 1px dashed var(--border-subtle);
    margin-top: 0;
}
details.gap-card .gap-card-summary-field {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    color: var(--text-secondary);
    font-size: 0.82rem;
}
details.finding-card .finding-card-summary-desc {
    color: var(--text-primary);
    font-size: 0.92rem;
    font-weight: 500;
    flex: 1 1 auto;
    min-width: 200px;
}
details.finding-card .finding-card-summary-category {
    color: var(--text-muted); font-size: 0.74rem;
    text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600;
}

/* Score headline tile (used for completeness / alignment / consistency index). */
.score-tile {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    margin-bottom: 14px;
    display: inline-block; min-width: 220px;
}
.score-tile-label {
    color: var(--text-secondary); font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;
    margin-bottom: 4px;
}
.score-tile-value {
    font-size: 2.4rem; font-weight: 700; line-height: 1.1;
}
.score-tile-value .score-tile-denom {
    color: var(--text-muted); font-size: 1rem; font-weight: 500;
}
.score-tile-sub {
    color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px;
}

/* Finding card (used by review on Plan from Brief). */
.finding-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--text-muted);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.finding-card.finding-blocker { border-left-color: var(--danger); }
.finding-card.finding-error   { border-left-color: var(--danger); }
.finding-card.finding-warning { border-left-color: var(--warning); }
.finding-card.finding-info    { border-left-color: var(--info); }
.finding-card .finding-head {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    flex-wrap: wrap;
}
.finding-card .finding-category {
    color: var(--text-muted); font-size: 0.74rem;
    text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600;
}
.finding-card .finding-desc {
    color: var(--text-primary); font-size: 0.92rem;
    line-height: 1.55; margin: 4px 0 8px 0;
}
.finding-card .finding-detail {
    color: var(--text-secondary); font-size: 0.85rem;
    line-height: 1.55; margin-top: 4px;
}
.finding-card .finding-detail-label {
    color: var(--text-muted); font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600;
    margin-right: 4px;
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
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05),
                0 4px 14px rgba(15, 23, 42, 0.03);
}
.lumeo-kv th, .lumeo-kv td {
    padding: 10px 14px;
    text-align: left;
    font-size: 0.88rem;
    border-bottom: 1px solid var(--border-subtle);
    vertical-align: top;
}
.lumeo-kv tbody tr:nth-child(even) td { background: rgba(238, 241, 247, 0.4); }
.lumeo-kv tbody tr:hover td { background: var(--accent-soft); }
.lumeo-kv tr:last-child td { border-bottom: none; }
.lumeo-kv thead th {
    background: linear-gradient(180deg, #EEF2FF 0%, #E0E7FF 100%);
    color: var(--accent);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
    border-bottom: 1px solid rgba(79, 70, 229, 0.18);
}
.lumeo-kv td.kv-field {
    color: var(--text-secondary);
    width: 30%;
    font-weight: 500;
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
    border: 1px solid var(--border-subtle);
}

/* Expander frame */
details {
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    margin-bottom: 8px;
    background: var(--bg-panel);
}
details > summary { padding: 10px 14px !important; color: var(--text-primary); }

/* Streamlit native expanders use a different DOM — give them the same treatment. */
[data-testid="stExpander"] {
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    background: var(--bg-panel);
    margin-bottom: 8px;
}

/* Buttons — primary uses the indigo gradient. White text is enforced on every
   descendant so Streamlit's internal label spans inherit it (some Streamlit
   versions wrap the label in a span that picks up `color: var(--text-primary)`
   from a higher-up rule). The same treatment is applied to download buttons
   and form submit buttons since they share the kind="primary" attribute. */
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
button[kind="primary"][data-testid="baseButton-primary"],
button[kind="primaryFormSubmit"] {
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%) !important;
    border: 1px solid var(--accent) !important;
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(79, 70, 229, 0.25);
}
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] *,
.stDownloadButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] *,
button[kind="primary"][data-testid="baseButton-primary"],
button[kind="primary"][data-testid="baseButton-primary"] *,
button[kind="primaryFormSubmit"],
button[kind="primaryFormSubmit"] * {
    color: #FFFFFF !important;
    fill: #FFFFFF !important;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
button[kind="primary"][data-testid="baseButton-primary"]:hover,
button[kind="primaryFormSubmit"]:hover {
    background: linear-gradient(135deg, #4338CA 0%, #4F46E5 100%) !important;
    border-color: var(--accent-hover) !important;
    box-shadow: 0 3px 10px rgba(79, 70, 229, 0.35);
}
.stButton > button[kind="secondary"] {
    background: var(--bg-panel);
    color: var(--text-primary) !important;
    border: 1px solid var(--border-strong);
}
.stButton > button[kind="secondary"]:hover { background: var(--bg-elevated); }

/* Inputs — flat white surface, soft border, rounded corners, accent focus
   ring. The default Streamlit widget chrome ships with square corners on the
   input element AND on the wrapper div that holds the dropdown chevron, which
   reads as visually "off" against the rest of the rounded UI. We round both
   the input and its wrapper, and target the selectbox chevron container so
   the right edge of dropdowns matches the left edge. */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div,
.stNumberInput > div > div > input,
.stMultiSelect > div > div > div,
.stDateInput > div > div > input,
.stTimeInput > div > div > input {
    background: var(--bg-input) !important;
    border: 1px solid var(--border-strong) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}
/* The wrapper divs around inputs/selectboxes — Streamlit nests several layers
   that each contribute a clipping region; if any layer has 0 radius, the
   visible corner stays square. Rounding the BaseWeb root and its first
   child covers every widget variant we use. */
.stTextInput div[data-baseweb="input"],
.stTextArea div[data-baseweb="textarea"],
.stSelectbox div[data-baseweb="select"],
.stMultiSelect div[data-baseweb="select"],
.stNumberInput div[data-baseweb="input"],
.stDateInput div[data-baseweb="input"],
.stTimeInput div[data-baseweb="input"] {
    border-radius: 8px !important;
}
/* Selectbox internals: the displayed value cell and the chevron button on the
   right both need rounding (or the right edge of the dropdown shows a square
   corner where the chevron container clips). */
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
    border-radius: 8px !important;
}
.stSelectbox [role="combobox"],
.stMultiSelect [role="combobox"] {
    border-radius: 8px !important;
}
/* The chevron icon container that sits at the right edge of every selectbox
   — Streamlit gives it its own div which inherits 0 radius. */
.stSelectbox div[data-baseweb="select"] [data-testid="stSelectbox-chevron"],
.stSelectbox div[data-baseweb="select"] svg {
    border-radius: 0 8px 8px 0;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stNumberInput > div > div > input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-soft) !important;
    border-radius: 8px !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: var(--text-secondary);
    padding: 8px 14px;
    border-radius: 8px 8px 0 0;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}
</style>
"""


def inject_global_css() -> None:
    """Inject global CSS on every page render.

    The earlier "inject once per session" optimization caused the stylesheet to be
    DROPPED when Streamlit re-rendered a page on sidebar click — the previous page's
    `<style>` tag was no longer in the DOM, and the new page skipped re-injection
    because the session-state flag was set, leaving plain unstyled text.

    Re-injecting on every render is the right answer: browsers de-duplicate identical
    `<style>` blocks cheaply, and the user-visible result is consistent styling on
    refresh AND on every navigation click."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Top header — centered product wordmark
# ---------------------------------------------------------------------------


def top_header(*, subtitle: str | None = None) -> None:
    """Inject the global full-width dark header bar.

    The bar is `position: fixed` at the top of the viewport so it spans the entire
    width — across both the sidebar and the main content panel. The Streamlit
    default toolbar is hidden by the global stylesheet so the bar sits flush with
    the viewport edge.

    `subtitle` is accepted for backwards compatibility (legacy callsites); the
    constant `PRODUCT_TAGLINE` is rendered next to the wordmark regardless."""
    _ = subtitle  # legacy param; canonical tagline always rendered
    st.markdown(
        "<div class='lumeo-global-header'>"
        "<div class='lumeo-global-header-inner'>"
        "<span class='gh-dot'></span>"
        f"<span class='gh-name'>{PRODUCT_NAME}</span>"
        "<span class='gh-divider'>|</span>"
        f"<span class='gh-tag'>{_safe_text(PRODUCT_TAGLINE)}</span>"
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
    """Hero banner. Renders the page title + subtitle in a left-edge-accented panel.

    The `kicker` and `tags` parameters are accepted for backwards compatibility but are
    no longer rendered — per UI feedback the per-page banner now shows only title +
    subtitle, and the centered Lumeo wordmark above carries the brand."""
    _ = (tags, kicker)  # legacy parameters retained for callsite compat; intentionally unused
    st.markdown(
        "<div class='lumeo-banner'>"
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
    """Render a section heading with an optional right-aligned action label.

    The `kicker` parameter is accepted for backwards compatibility but is no longer
    rendered — page authors should use plain section titles instead of `Step 1 · X`
    style overlines."""
    _ = kicker  # legacy parameter; intentionally unused
    action_html = (
        f"<div class='lumeo-section-action'>{_safe_text(action)}</div>" if action else ""
    )
    st.markdown(
        "<div class='lumeo-section'>"
        "<div class='lumeo-section-text'>"
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


def callout(message_html: str, *, kind: Literal["info", "warning", "success"] = "info") -> None:
    """Soft inline callout — accent-colored panel for guidance text. `message_html` is
    rendered as HTML so callers may include `<strong>`, `<a>`, etc."""
    cls = {"info": "lumeo-callout", "warning": "lumeo-callout lumeo-callout-warning",
           "success": "lumeo-callout lumeo-callout-success"}[kind]
    st.markdown(f"<div class='{cls}'>{message_html}</div>", unsafe_allow_html=True)


def score_legend() -> None:
    """Render the compact three-score legend as a single strip with three colored
    label chips and one-line definitions. Designed to be visually attached to the
    page banner (use `render_banner_with_legend` to fuse them)."""
    st.markdown(
        "<div class='lumeo-legend-strip'>"
        "  <div class='lumeo-legend-item'>"
        "    <span class='lumeo-legend-chip legend-blue'>Completeness</span>"
        "    <span class='lumeo-legend-text'>How complete the brief is.</span>"
        "  </div>"
        "  <div class='lumeo-legend-item'>"
        "    <span class='lumeo-legend-chip legend-mint'>Voice score</span>"
        "    <span class='lumeo-legend-text'>Closeness between AI-generated copy and the "
        "brand voice fingerprint.</span>"
        "  </div>"
        "  <div class='lumeo-legend-item'>"
        "    <span class='lumeo-legend-chip legend-violet'>Alignment</span>"
        "    <span class='lumeo-legend-text'>How well the generated plan addresses the brief.</span>"
        "  </div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_banner_with_legend(title: str, subtitle: str) -> None:
    """Render the page banner immediately followed by the compact score legend strip,
    visually joined as one container. Used on Plan from Brief so the explanation sits
    inside the same panel as the page title."""
    st.markdown(
        "<div class='lumeo-banner banner-with-legend'>"
        f"<h1>{_safe_text(title)}</h1>"
        f"<p>{_safe_text(subtitle)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    score_legend()


def step_rail(steps: list[tuple[str, str]]) -> None:
    """Render a full-width horizontal step rail with arrow separators.

    `steps` is a list of `(label, state)` tuples where state is one of
    `done` | `current` | `pending`. The pills size equally to span the row."""
    parts: list[str] = []
    for i, (label, state) in enumerate(steps):
        if i:
            parts.append("<span class='step-arrow'>→</span>")
        cls = state if state in {"done", "current", "pending"} else "pending"
        parts.append(f"<div class='step-pill {cls}'>{_safe_text(label)}</div>")
    st.markdown(
        "<div class='lumeo-step-rail'>" + "".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


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
