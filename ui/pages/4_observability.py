"""P8 — Observability. Pick a recent session, view live cost meter + trace + replay."""
from __future__ import annotations

import os
import time

import httpx
import streamlit as st

from ui.components.cost_meter import render_cost_meter
from ui.components.trace_view import render_trace_view
from ui.styles import inject_global_css, render_banner, styled_error


st.set_page_config(page_title="Axion · Observability", layout="wide")
inject_global_css()
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_get(path: str) -> tuple[int, list | dict]:
    with httpx.Client(timeout=10.0) as c:
        r = c.get(f"{API_BASE}{path}")
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"error": r.text}


render_banner(
    "Observability",
    "Pick a recent session to inspect cost, trace timeline, and replay. Each LLM call writes one row; "
    "cache hits are flagged so warmed demos can be told apart from live runs.",
    tags=["P8", "trace"],
)

code, sessions = _api_get("/api/v1/sessions/recent?limit=20")
if code != 200 or not isinstance(sessions, list):
    styled_error("Could not fetch recent sessions. Is the API up?", title="Sessions unavailable")
    st.stop()

if not sessions:
    st.info("No sessions yet. Run a brief through page 1 to populate.")
    st.stop()

options = {
    f"{s['started_at'][:19]} · {s['entry_point']} · {s['n_trace_events']} events · ${s['cost_usd']:.4f}": s["id"]
    for s in sessions
}
choice = st.selectbox("Session", list(options.keys()))
session_id = options[choice] if choice else None

st.markdown("### Cost meter")
render_cost_meter(session_id)

c1, c2 = st.columns([1, 4])
with c1:
    auto_refresh = st.checkbox("Auto-refresh every 2s", value=False, help="Polls the cost endpoint live.")
with c2:
    if st.button("Refresh now"):
        st.rerun()

st.markdown("### Trace timeline")
render_trace_view(session_id)

st.markdown("### Replay")
if st.button("Replay this session"):
    code, steps = _api_get(f"/api/v1/sessions/{session_id}/replay")
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

if auto_refresh and session_id:
    time.sleep(2.0)
    st.rerun()
