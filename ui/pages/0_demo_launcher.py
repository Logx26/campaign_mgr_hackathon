"""P9 — One-click demo launcher.

Four pre-staged demos. Each card shows what'll happen, an "armed" badge if the seed
script has been run (Redis marker present), and a single CTA that deep-links to the
right workflow page with state pre-filled.

If the API is unreachable the launcher still renders the cards and routes the user
to the fallback page (see `ui/pages/_fallback.py`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import streamlit as st

from ui.styles import inject_global_css, render_banner, severity_pill, styled_error


st.set_page_config(page_title="Axion · Demo Launcher", layout="wide")
inject_global_css()
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ---------------------------------------------------------


def _is_armed(redis_key: str) -> bool:
    """Best-effort armed check — calls a tiny health endpoint then a redis lookup via API."""
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"{API_BASE}/api/v1/demo/armed?key={redis_key}")
            if r.status_code == 200:
                return bool(r.json().get("armed"))
    except Exception:
        return False
    return False


def _api_alive() -> bool:
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"{API_BASE}/api/v1/health")
            return r.status_code == 200
    except Exception:
        return False


# ---------- banner ---------------------------------------------------------

render_banner(
    "Axion · One-click demo launcher",
    "Four pre-staged campaign management workflows, each runnable in under 90 seconds. "
    "Cards show whether the demo is armed (cache warmed by the dry-run script).",
    tags=["P9", "demo"],
)

api_alive = _api_alive()
if not api_alive:
    styled_error(
        "The API is not responding. Start the FastAPI server and refresh, or click "
        "<b>Fallback view</b> on any card to render from the cached payload.",
        title="API offline",
    )


# ---------- demo grid ------------------------------------------------------

DEMOS = [
    {
        "letter": "A",
        "title": "Happy path — complete brief → plan",
        "subtitle": "A complete enterprise SaaS brief flows through intake → plan → review without clarification.",
        "narrative": "Shows the system handles a strong input cleanly. ~60 seconds to a reviewable plan.",
        "cta": "Open W1",
        "page_target": "1_plan_from_brief",
        "redis_key": None,  # uses DB session, not Redis
        "tags": ["W1", "happy-path"],
    },
    {
        "letter": "B",
        "title": "Kickoff — ambiguous brief → clarify → plan",
        "subtitle": "Sample Brief A has 5 hard gaps. Watch the clarification loop turn red completeness into green.",
        "narrative": "The differentiator. 3-5 typed questions, suggested defaults, gap list shrinks live.",
        "cta": "Open W1 (kickoff brief)",
        "page_target": "1_plan_from_brief",
        "redis_key": None,
        "tags": ["W1", "kickoff"],
    },
    {
        "letter": "C",
        "title": "Standalone QA — paste mismatched pair",
        "subtitle": "Enterprise brief paired with an SMB-tone plan. Critic catches coverage + governance violations.",
        "narrative": "Severity-emoji findings + Top Issues panel + alignment score. Built on the same Critic as W1.",
        "cta": "Open W2",
        "page_target": "2_qa_existing_plan",
        "redis_key": "demo:c:armed",
        "tags": ["W2", "QA"],
    },
    {
        "letter": "D",
        "title": "Multi-asset consistency — 5 staged drift assets",
        "subtitle": "3 'AI-powered' + 2 'AI-assisted' + 3 'Book a demo' + 2 'Schedule a call' across 5 assets.",
        "narrative": "Greedy cosine clustering picks AI-powered/AI-assisted as one cluster; canonical resolver cites brand_book_§3.1.",
        "cta": "Open W3",
        "page_target": "3_consistency_scan",
        "redis_key": "demo:d:armed",
        "tags": ["W3", "consistency"],
    },
]


cols = st.columns(2)
for i, demo in enumerate(DEMOS):
    col = cols[i % 2]
    armed = bool(demo["redis_key"]) and _is_armed(demo["redis_key"])
    with col:
        st.markdown(
            f"<div class='axion-card'>"
            f"<h4>Demo {demo['letter']} · {demo['title']}</h4>"
            f"<div style='margin-bottom:6px'>"
            + " ".join(severity_pill("info", t) for t in demo["tags"])
            + (severity_pill("success", "ARMED") if armed else (severity_pill("neutral", "needs seed") if demo["redis_key"] else ""))
            + "</div>"
            f"<p style='color:var(--text-2); font-size:0.92rem; margin:6px 0 4px 0'>{demo['subtitle']}</p>"
            f"<p style='color:var(--text-1); font-size:0.85rem; margin:0 0 10px 0'><em>{demo['narrative']}</em></p>"
            "</div>",
            unsafe_allow_html=True,
        )
        b1, b2 = st.columns([2, 1])
        with b1:
            if st.button(demo["cta"], key=f"open_{demo['letter']}", type="primary", use_container_width=True):
                # Set a session-state hint that the target page can use to auto-load.
                st.session_state["_launch_demo"] = demo["letter"]
                try:
                    st.switch_page(f"pages/{demo['page_target']}.py")
                except Exception:
                    st.info(f"Open the **{demo['page_target']}** page from the sidebar.")
        with b2:
            if st.button("Fallback view", key=f"fallback_{demo['letter']}", use_container_width=True):
                st.session_state["_launch_demo"] = demo["letter"]
                st.session_state["_force_fallback"] = True
                try:
                    st.switch_page("pages/_fallback.py")
                except Exception:
                    st.info("Open the **fallback** page from the sidebar.")


# ---------- runbook --------------------------------------------------------

st.markdown("### Pre-flight runbook")
st.markdown(
    """
1. `docker compose -f docker-compose.infra.yml up -d` — Postgres / Redis / Qdrant healthy.
2. `python -m pytest tests/unit -q` — all green.
3. `python scripts/build_brand_voice_fingerprint.py` — Axion fingerprint persisted.
4. `python scripts/seed_demo_a.py && python scripts/seed_demo_b.py && python scripts/seed_demo_c.py && python scripts/seed_demo_d.py` — arm all demos.
5. `python scripts/replay_session.py --with-plan` — warm every cache (one-time, ~3 min).
6. **Do not flush Redis** between dry-run and real demo.
    """
)
