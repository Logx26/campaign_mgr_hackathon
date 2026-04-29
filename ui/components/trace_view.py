"""Trace view component — pulls /sessions/{id}/trace and renders rows in a table."""
from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st


API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def render_trace_view(session_id: str | None) -> list[dict] | None:
    if not session_id:
        st.caption("No active session.")
        return None
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{API_BASE}/api/v1/sessions/{session_id}/trace")
            if r.status_code != 200:
                st.caption(f"Trace unavailable ({r.status_code}).")
                return None
            events = r.json()
    except Exception as exc:
        st.caption(f"Trace error: {exc}")
        return None

    if not events:
        st.info("No trace events recorded yet for this session.")
        return events

    rows = [
        {
            "ts": e["timestamp"],
            "agent": e["agent_name"],
            "prompt": e.get("prompt_name") or "—",
            "cache": "✅" if e.get("cache_hit") else "❌",
            "latency_ms": e.get("latency_ms", 0),
            "tokens_in": e.get("tokens_in", 0),
            "tokens_out": e.get("tokens_out", 0),
            "cost_usd": float(e.get("cost_usd", 0) or 0),
            "error": (e.get("error") or "")[:80],
        }
        for e in events
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    return events
