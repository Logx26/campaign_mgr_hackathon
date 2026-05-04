"""Quality Dashboard — gap-detection + plan-completeness across the reference brief set.

System page. Run `python scripts/run_eval.py --tag baseline` to record a row.

Metrics are presented as percentages (0–100) instead of fractions (0–1) so the
chart fills meaningfully even at modest scores. Two summary tiles use traffic-
light coloring and delta-from-previous-run indicators so a single run is still
useful — the user gets a snapshot, not a flat zero-height line.
"""
from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.styles import (
    PRODUCT_NAME,
    callout,
    inject_global_css,
    render_banner,
    section_header,
    top_header,
    traffic_color,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Quality Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


render_banner(
    "Quality dashboard",
    "Tracks how well the AI catches gaps and produces complete plans across the reference brief set. "
    "Scores hold steady or trend up; sudden drops signal a regression.",
    kicker="System · Quality",
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
    callout(
        "<strong>No quality runs yet.</strong><br>"
        "Run <code>python scripts/run_eval.py --tag baseline</code> from the project root to record "
        "a baseline. The chart populates after each subsequent run.",
        kind="info",
    )
    st.stop()


rows = []
for r in runs:
    s = r.get("summary") or {}
    items_total = int(s.get("items_total", 0))
    items_executed = int(s.get("items_executed", 0))
    rows.append(
        {
            "run_at": r["run_at"],
            "tag": r.get("tag") or "—",
            "items_total": items_total,
            "items_executed": items_executed,
            "items_errored": int(s.get("items_errored", 0)),
            "gap_catch_pct": float(s.get("gap_catch_rate", 0.0)) * 100.0,
            "plan_completeness_pct": float(s.get("plan_completeness_score", 0.0)) * 100.0,
            "completion_pct": (
                100.0 * items_executed / items_total if items_total else 0.0
            ),
        }
    )

df = pd.DataFrame(rows).sort_values("run_at").reset_index(drop=True)
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) >= 2 else None


def _delta_pct(field: str) -> str | None:
    if prev is None:
        return None
    diff = float(latest[field]) - float(prev[field])
    if abs(diff) < 0.05:
        return None
    return f"{diff:+.1f} pp"


# ---- Summary tiles --------------------------------------------------------
# Traffic-color the headline metrics so a 36% gap-catch reads visually different
# from an 84%, even on the same axis. The percentage view replaces the prior
# 0.36 vs 0.84 fractional rendering that was easy to misread.
section_header("Latest run")
c1, c2, c3, c4 = st.columns(4)

gc = float(latest["gap_catch_pct"])
pc = float(latest["plan_completeness_pct"])

c1.metric(
    "Gap detection",
    f"{gc:.0f}%",
    delta=_delta_pct("gap_catch_pct"),
    help="Share of expected gaps the AI surfaces. Higher = better.",
)
c2.metric(
    "Plan completeness",
    f"{pc:.0f}%",
    delta=_delta_pct("plan_completeness_pct"),
    help="Average completeness of generated plans. Higher = better.",
)
c3.metric(
    "Briefs evaluated",
    f"{int(latest['items_executed'])}/{int(latest['items_total'])}",
    help="How many briefs in the reference set the run actually executed.",
)
c4.metric(
    "Failed runs",
    int(latest["items_errored"]),
    help="Briefs that errored during eval. Should always be 0.",
)


# ---- Health gauges --------------------------------------------------------
# Two compact gauges replace the empty-looking line chart when only a single
# run exists. Plotly indicators with traffic-color thresholds give an
# immediate read on each metric without depending on time-series data.
gc_color = traffic_color(gc).replace("var(--success)", "#16A34A").replace(
    "var(--warning)", "#CA8A04"
).replace("var(--danger)", "#DC2626")
pc_color = traffic_color(pc).replace("var(--success)", "#16A34A").replace(
    "var(--warning)", "#CA8A04"
).replace("var(--danger)", "#DC2626")

g1, g2 = st.columns(2)
with g1:
    fig_gc = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=gc,
            number={"suffix": "%", "font": {"size": 36, "color": "#0F172A"}},
            title={"text": "Gap detection", "font": {"size": 14, "color": "#475569"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#94A3B8"},
                "bar": {"color": gc_color, "thickness": 0.7},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "rgba(220,38,38,0.10)"},
                    {"range": [50, 80], "color": "rgba(202,138,4,0.10)"},
                    {"range": [80, 100], "color": "rgba(22,163,74,0.10)"},
                ],
            },
        )
    )
    fig_gc.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=240,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_gc, use_container_width=True)

with g2:
    fig_pc = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pc,
            number={"suffix": "%", "font": {"size": 36, "color": "#0F172A"}},
            title={"text": "Plan completeness", "font": {"size": 14, "color": "#475569"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#94A3B8"},
                "bar": {"color": pc_color, "thickness": 0.7},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "rgba(220,38,38,0.10)"},
                    {"range": [50, 80], "color": "rgba(202,138,4,0.10)"},
                    {"range": [80, 100], "color": "rgba(22,163,74,0.10)"},
                ],
            },
        )
    )
    fig_pc.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=240,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_pc, use_container_width=True)


# ---- Trend (only when we have ≥2 runs) ------------------------------------
if len(df) >= 2:
    section_header("Trend over time")
    chart_df = df.melt(
        id_vars=["run_at", "tag"],
        value_vars=["gap_catch_pct", "plan_completeness_pct", "completion_pct"],
        var_name="metric",
        value_name="score",
    )
    metric_label = {
        "gap_catch_pct": "Gap detection",
        "plan_completeness_pct": "Plan completeness",
        "completion_pct": "Completion rate",
    }
    chart_df["metric"] = chart_df["metric"].map(metric_label)
    fig = px.line(
        chart_df,
        x="run_at",
        y="score",
        color="metric",
        markers=True,
        range_y=[0.0, 105.0],
        color_discrete_map={
            "Gap detection": "#4F46E5",
            "Plan completeness": "#0EA5E9",
            "Completion rate": "#14B8A6",
        },
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#0F172A"),
        yaxis_title="Score (%)",
        xaxis_title="Run timestamp",
        legend_title_text="",
        height=320,
    )
    fig.update_yaxes(gridcolor="#E2E6EF", zerolinecolor="#E2E6EF")
    fig.update_xaxes(gridcolor="#E2E6EF", zerolinecolor="#E2E6EF")
    st.plotly_chart(fig, use_container_width=True)
else:
    callout(
        f"Single-run snapshot: <strong>{gc:.0f}%</strong> gap detection · "
        f"<strong>{pc:.0f}%</strong> plan completeness · "
        f"<strong>{int(latest['items_executed'])}/{int(latest['items_total'])}</strong> "
        "briefs evaluated. Trend chart activates after the second run.",
        kind="info",
    )


# ---- Recent runs table ----------------------------------------------------
section_header("Recent runs")
display_df = df.sort_values("run_at", ascending=False).reset_index(drop=True).copy()
display_df["gap_catch_pct"] = display_df["gap_catch_pct"].map(lambda v: f"{v:.1f}%")
display_df["plan_completeness_pct"] = display_df["plan_completeness_pct"].map(
    lambda v: f"{v:.1f}%"
)
display_df["completion_pct"] = display_df["completion_pct"].map(
    lambda v: f"{v:.1f}%"
)
display_df = display_df.rename(
    columns={
        "run_at": "Run at",
        "tag": "Tag",
        "items_total": "Total briefs",
        "items_executed": "Executed",
        "items_errored": "Errored",
        "gap_catch_pct": "Gap detection",
        "plan_completeness_pct": "Plan completeness",
        "completion_pct": "Completion",
    }
)
st.dataframe(display_df, use_container_width=True, hide_index=True)
