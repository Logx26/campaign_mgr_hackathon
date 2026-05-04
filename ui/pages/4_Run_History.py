"""Run History — inspect cost, latency, and cache behavior for each session.

System-side page (not a primary workflow). Renders the cost meter + trace timeline +
optional replay timeline for a chosen session.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

from ui.components.cost_meter import render_cost_meter
from ui.components.trace_view import render_trace_view
from ui.styles import (
    PRODUCT_NAME,
    inject_global_css,
    render_banner,
    section_header,
    styled_error,
    top_header,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Run History",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_get(path: str, timeout: float = 5.0) -> tuple[int, list | dict]:
    """Tight default timeout — Run History should never hang waiting on the backend.
    A 5-second cap keeps the page responsive even if the API is slow or absent."""
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{API_BASE}{path}")
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, {"error": r.text}
    except Exception as exc:
        return 0, {"error": str(exc)}


render_banner(
    "Run history",
    "Inspect spend, latency, and cache behavior for each campaign workflow session. Each AI call "
    "writes one trace event; cache hits land at $0 spend by design.",
)

code, sessions = _api_get("/api/v1/sessions/recent?limit=20")
if code != 200 or not isinstance(sessions, list):
    styled_error(
        "Could not fetch recent sessions. Confirm the backend is running.",
        title="Sessions unavailable",
    )
    st.stop()

if not sessions:
    st.info("No sessions yet. Run a brief through **Plan from Brief** to populate.")
    st.stop()

# Cost is intentionally NOT shown in the dropdown label — it's redundant with
# the Spend metric strip below, and the prior label format showed a stale
# $0.0000 because `sessions.cost_usd` is rarely written (the authoritative
# ledger is `trace_events.cost_usd`). The metric strip pulls from the
# events-summed snapshot, so cost there is always current.
options = {
    f"{s['started_at'][:19]} · {s['entry_point']} · {s['n_trace_events']} events": s["id"]
    for s in sessions
}
# Constrain the dropdown to roughly half the page width so it doesn't span
# the whole row — the values fit comfortably in a narrower container and the
# right half stays free for whitespace.
sel_col, _spacer = st.columns([1, 1])
with sel_col:
    choice = st.selectbox("Session", list(options.keys()))
session_id = options[choice] if choice else None

section_header("Spend")
render_cost_meter(session_id)

# Manual refresh button only — the previous `time.sleep(2.0); st.rerun()` auto-refresh
# loop made the page unresponsive when users navigated away. Streamlit's script thread
# can deadlock when a navigation event fires mid-sleep, requiring a server restart.
# A manual refresh button is the safe pattern for a "fresh data on demand" surface.
if st.button("Refresh", help="Fetch the latest cost + trace from the backend."):
    st.rerun()

section_header("Trace timeline")
render_trace_view(session_id)

section_header("Replay")
if st.button("Replay this session"):
    code, steps = _api_get(f"/api/v1/sessions/{session_id}/replay", timeout=10.0)
    if code != 200 or not isinstance(steps, list):
        styled_error("Replay endpoint did not return events.", title="Replay failed")
    elif not steps:
        st.info("No replay steps — session has no trace events.")
    else:
        progress = st.progress(0.0)
        log = st.empty()
        lines: list[str] = []
        for i, s in enumerate(steps):
            cache_tag = "⚡ cached" if s["cache_hit"] else "🟦 live"
            err = f" — ⚠️ {s['error']}" if s["error"] else ""
            lines.append(
                f"[{i+1:02d}] {s['agent_name']:<28} {cache_tag:<10} "
                f"{s['latency_ms']:>5}ms · ${s['cost_usd']:.5f}{err}"
            )
            log.code("\n".join(lines))
            progress.progress((i + 1) / len(steps))
        st.success(f"Replay complete — {len(steps)} steps.")
