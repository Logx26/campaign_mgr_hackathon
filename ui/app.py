"""Streamlit landing page — probes the API health and shows project status.

Multi-page UI is configured via files in `ui/pages/` (Streamlit auto-discovers them).
"""
from __future__ import annotations

import os

import httpx
import streamlit as st


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
        page_title="Campaign Management — AI Workflow",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Campaign Management — AI Workflow")
    st.caption(
        "Brief → clarification dialog → execution plan → critic + ledger → export. "
        "Phase 1 (Foundation) — agents not wired yet."
    )

    ok, payload = _probe_api()

    col1, col2 = st.columns([1, 3])
    with col1:
        if ok and payload.get("status") == "ok":
            st.success("API: OK")
        elif ok and payload.get("status") == "degraded":
            st.warning("API: degraded")
        else:
            st.error("API: unreachable")
    with col2:
        st.code(payload, language="json")

    st.divider()

    st.subheader("Status")
    st.markdown(
        """
        - **Phase:** P1 — Foundation
        - **Workflows planned:** W1 plan-from-brief, W2 standalone QA, W3 multi-asset consistency
        - **Stack:** LangGraph + FastAPI + Streamlit + Azure OpenAI + Postgres + Qdrant + Redis
        - See `../claude_plan_external.md` for the project journey, `../CLAUDE.md` for live status.
        """
    )

    st.subheader("Next steps")
    st.markdown(
        """
        1. P2 — Build the LLM gateway with cache + cost + structured-output enforcement.
        2. P3 — Brief Normalizer + Completeness rules + Ambiguity detector → ranked GapList.
        3. P4 — Clarifier + LangGraph HITL interrupt + Streamlit dialog.
        """
    )


if __name__ == "__main__":
    main()
