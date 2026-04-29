"""Streamlit landing page — Axion campaign workflow.

Drops the user into a polished landing card with API status + a "Launch demos" CTA.
Multi-page UI is configured via files in `ui/pages/` (Streamlit auto-discovers them).
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

from ui.styles import inject_global_css, render_banner, severity_pill, styled_error


def _api_base_url() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


def _probe_api() -> tuple[bool, dict]:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{_api_base_url()}/api/v1/health")
            r.raise_for_status()
            return True, r.json()
    except Exception as exc:
        return False, {"error": str(exc)}


def main() -> None:
    st.set_page_config(
        page_title="Axion · Campaign Workflow",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_css()

    render_banner(
        "Axion · AI Campaign Workflow",
        "Brief → clarify → plan → review → export. Three workflows from one platform — "
        "plan-from-brief, standalone QA, multi-asset consistency.",
        tags=["P9", "demo-ready"],
    )

    ok, payload = _probe_api()

    c1, c2 = st.columns([1, 3])
    with c1:
        if ok and payload.get("status") == "ok":
            st.markdown(severity_pill("success", "API · OK"), unsafe_allow_html=True)
        elif ok and payload.get("status") == "degraded":
            st.markdown(severity_pill("warning", "API · DEGRADED"), unsafe_allow_html=True)
        else:
            st.markdown(severity_pill("error", "API · OFFLINE"), unsafe_allow_html=True)
    with c2:
        if ok:
            st.code(payload, language="json")
        else:
            styled_error(
                "FastAPI service did not respond on the health endpoint. "
                "Start it with <code>uvicorn api.main:app --port 8000</code> and refresh.",
                title="API offline",
            )

    st.markdown("### Workflows")
    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            "<div class='axion-card'>"
            "<h4>W1 · Plan from Brief</h4>"
            "<p style='color:var(--text-2)'>Intake → clarify → generate plan → review + approve.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            "<div class='axion-card'>"
            "<h4>W2 · Standalone QA</h4>"
            "<p style='color:var(--text-2)'>Paste any brief + plan → severity-ranked findings with citations.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            "<div class='axion-card'>"
            "<h4>W3 · Consistency</h4>"
            "<p style='color:var(--text-2)'>3-30 assets → terminology + CTA drift → canonical recommendations.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='color:var(--text-2); margin-top:18px'>"
        "Open <strong>0 · Demo Launcher</strong> from the sidebar for one-click pre-staged flows. "
        "<strong>4 · Observability</strong> shows live cost + trace; <strong>5 · Eval Dashboard</strong> "
        "tracks regression on the 8-brief golden set."
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
