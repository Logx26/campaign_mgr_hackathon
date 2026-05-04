"""Streamlit cost meter component — pulls /sessions/{id}/cost and renders it as a metric strip."""
from __future__ import annotations

import os

import httpx
import streamlit as st


API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def render_cost_meter(session_id: str | None) -> dict | None:
    """Render the cost meter into the current Streamlit container. Returns the snapshot dict."""
    if not session_id:
        st.caption("No active session.")
        return None
    try:
        # 3s timeout — Run History should never hang on the backend. If the call
        # is slow the user gets an inline caption and can click Refresh manually.
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{API_BASE}/api/v1/sessions/{session_id}/cost")
            if r.status_code != 200:
                st.caption(f"Cost meter unavailable ({r.status_code}).")
                return None
            data = r.json()
    except Exception as exc:
        st.caption(f"Cost meter error: {exc}")
        return None

    cols = st.columns(5)
    cols[0].metric("Cost", f"${float(data['cost_usd']):.4f}")
    cols[1].metric("Calls", data["n_trace_events"])
    cols[2].metric("Cache hits", f"{int(data['n_cache_hits'])}")
    cols[3].metric("Cache hit rate", f"{float(data['cache_hit_rate']) * 100:.0f}%")
    cols[4].metric("Errors", data["n_errors"])
    return data
