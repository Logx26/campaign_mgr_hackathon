"""P8 — Eval Dashboard. Plot gap-catch rate + plan-completeness over time across stored EvalRun rows."""
from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

from ui.styles import inject_global_css, render_banner


st.set_page_config(page_title="Axion · Eval Dashboard", layout="wide")
inject_global_css()
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


render_banner(
    "Eval Dashboard",
    "Tracks regression on the 8-brief golden set. Run `python scripts/run_eval.py` to record a new row. "
    "Lines should hold steady or trend up; sudden drops indicate a prompt or agent regression.",
    tags=["P8", "regression"],
)


@st.cache_data(ttl=15.0)
def _load_runs() -> list[dict]:
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{API_BASE}/api/v1/eval/runs?limit=50")
            if r.status_code != 200:
                return []
            return r.json()
    except Exception:
        return []


runs = _load_runs()

if not runs:
    st.info(
        "No eval runs yet. From the project root run:\n\n"
        "```\npython scripts/run_eval.py --tag baseline\n```\n"
        "Then refresh this page."
    )
    st.stop()

rows = []
for r in runs:
    s = r.get("summary") or {}
    rows.append(
        {
            "run_at": r["run_at"],
            "tag": r.get("tag") or "—",
            "items_total": int(s.get("items_total", 0)),
            "items_executed": int(s.get("items_executed", 0)),
            "items_errored": int(s.get("items_errored", 0)),
            "gap_catch_rate": float(s.get("gap_catch_rate", 0.0)),
            "plan_completeness": float(s.get("plan_completeness_score", 0.0)),
        }
    )

df = pd.DataFrame(rows).sort_values("run_at")

# Headline numbers — most recent run.
latest = df.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest gap-catch", f"{latest['gap_catch_rate']:.2f}")
c2.metric("Latest plan-completeness", f"{latest['plan_completeness']:.2f}")
c3.metric("Items / total", f"{latest['items_executed']}/{latest['items_total']}")
c4.metric("Errors", int(latest["items_errored"]))

# Line chart
chart_df = df.melt(
    id_vars=["run_at", "tag"],
    value_vars=["gap_catch_rate", "plan_completeness"],
    var_name="metric",
    value_name="score",
)
fig = px.line(
    chart_df,
    x="run_at",
    y="score",
    color="metric",
    markers=True,
    title="Eval metrics over time",
    range_y=[0.0, 1.05],
)
st.plotly_chart(fig, use_container_width=True)

# Recent-runs table
st.markdown("### Recent runs")
st.dataframe(
    df.sort_values("run_at", ascending=False).reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)
