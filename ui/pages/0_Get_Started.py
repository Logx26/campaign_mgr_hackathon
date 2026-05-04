"""Get Started — pre-staged sample workflows.

Each card opens a real workflow with sample data pre-filled. Switch to your own brief /
plan / assets at any time.

Demo data loading lives here, not on the destination pages, so it's deterministic
across `st.switch_page` calls — by the time the next page mounts, the data is
already in `session_state`. Pages that don't see `_launch_demo` (i.e. opened from
the sidebar instead of from this page) render empty as the user requested.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import streamlit as st
import yaml as _yaml

from ui.styles import (
    PRODUCT_NAME,
    inject_global_css,
    render_banner,
    styled_error,
    top_header,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Get Started",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_alive() -> bool:
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"{API_BASE}/api/v1/health")
            return r.status_code == 200
    except Exception:
        return False


render_banner(
    "Walk through the studio in five minutes",
    "Each card opens a real workflow with a sample input pre-filled. Edit the input, swap "
    "to your own data, or restart any time.",
)

if not _api_alive():
    styled_error(
        "The backend service is not responding. Start it with "
        "<code>uvicorn api.main:app --port 8000</code> and refresh this page.",
        title="API offline",
    )


# ---------------------------------------------------------------------------
# Workflow definitions
# ---------------------------------------------------------------------------

WORKFLOWS = [
    {
        "letter": "A",
        "icon": "✨",
        "title": "Generate a complete plan",
        "subtitle": "A clean enterprise brief flows straight to a reviewable plan.",
        "body": "See the headline workflow end-to-end: brief → analyze → generate plan → "
                "review → approve. Sample is a complete enterprise B2B SaaS campaign.",
        "cta": "Open Plan from Brief",
        "page_target": "pages/1_Plan_from_Brief.py",
    },
    {
        "letter": "B",
        "icon": "💬",
        "title": "Resolve gaps before planning",
        "subtitle": "A vague brief surfaces 5 gaps. Answer 4 typed questions, watch the score climb.",
        "body": "The clarification differentiator. A brief missing budget, dates, and metrics "
                "produces typed questions; your answers update the brief; analysis re-runs to "
                "show the new completeness score.",
        "cta": "Open Plan from Brief (vague brief)",
        "page_target": "pages/1_Plan_from_Brief.py",
    },
    {
        "letter": "C",
        "icon": "🛡️",
        "title": "Verify a brief's quality",
        "subtitle": "Surface gaps and ambiguities before you commit to plan generation.",
        "body": "Use Brief QA to score a brief's completeness and surface what's "
                "ambiguous. The sample brief produces a mix of hard and soft gaps, "
                "see how the analyzer reasons about coverage and ambiguity.",
        "cta": "Open Brief QA",
        "page_target": "pages/2_Brief_QA.py",
    },
    {
        "letter": "D",
        "icon": "🔍",
        "title": "Scan assets for terminology drift",
        "subtitle": "Sample assets cluster 'AI-powered' vs 'AI-assisted' and recommend a canonical.",
        "body": "Greedy cosine clustering catches the variant; the canonical resolver cites "
                "the brand dictionary. Use this on real asset libraries to enforce brand "
                "consistency across marketing.",
        "cta": "Open Asset Consistency",
        "page_target": "pages/3_Asset_Consistency.py",
    },
]


# ---------------------------------------------------------------------------
# Render — 2x2 grid via st.columns. Each card has equal min-height via the
# `.workflow-card` CSS in styles.py; the Streamlit button sits below the card
# and aligns naturally because all four cards have the same height.
# ---------------------------------------------------------------------------

for row_start in (0, 2):
    cols = st.columns(2, gap="medium")
    for offset, col in enumerate(cols):
        i = row_start + offset
        if i >= len(WORKFLOWS):
            continue
        wf = WORKFLOWS[i]
        with col:
            st.markdown(
                "<div class='workflow-card'>"
                f"<div class='workflow-icon'>{wf['icon']}</div>"
                f"<h3>{wf['title']}</h3>"
                f"<p><strong>{wf['subtitle']}</strong></p>"
                f"<p style='margin-top:10px'>{wf['body']}</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button(wf["cta"], key=f"open_{wf['letter']}", type="primary",
                         use_container_width=True):
                # Pre-load demo D's asset list synchronously so it's already
                # in session_state by the time Asset Consistency mounts. The
                # earlier "load on the destination page" approach was
                # unreliable across `st.switch_page` timing on some Streamlit
                # builds.
                if wf["letter"] == "D":
                    seeds_root = (
                        Path(__file__).resolve().parents[2]
                        / "seeds"
                        / "sample_assets"
                    )
                    yaml_paths = (
                        sorted(seeds_root.glob("asset_*.yaml"))
                        if seeds_root.exists()
                        else []
                    )
                    assets: list[dict] = []
                    for p in yaml_paths:
                        try:
                            data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                        except Exception:
                            continue
                        assets.append(
                            {
                                "source": str(data.get("source_name") or ""),
                                "channel": str(data.get("channel") or ""),
                                "audience": str(data.get("audience_hint") or ""),
                                "body": str(data.get("body") or "").strip(),
                            }
                        )
                    st.session_state["_demo_d_assets"] = assets
                st.session_state["_launch_demo"] = wf["letter"]
                try:
                    st.switch_page(wf["page_target"])
                except Exception:
                    styled_error(
                        f"Could not switch pages automatically. Open <strong>{wf['cta']}</strong> "
                        "from the sidebar to continue.",
                        title="Navigation hint",
                    )


# ---------------------------------------------------------------------------
# Reference card — score legend explanation tucked at the bottom.
# ---------------------------------------------------------------------------

st.markdown(
    "<div class='lumeo-card' style='margin-top:32px'>"
    "<h4 style='margin-bottom:10px'>How the studio works</h4>"
    "<div class='lumeo-card-body'>"
    "<strong>Completeness</strong> shows how much your brief covers (rule-driven, 0–100). "
    "<strong>Voice score</strong> shows how on-brand each AI-drafted copy reads (cosine vs. "
    "stored brand voice fingerprint, 0–100; 50–70 is normal for B2B). "
    "<strong>Alignment</strong> shows how well the generated plan addresses the brief, "
    "after the Critic and governance scanners run. These measure different things — a "
    "complete brief can produce a plan the Critic flags, and that is exactly the value of "
    "the QA layer."
    "</div>"
    "</div>",
    unsafe_allow_html=True,
)
