"""Brief QA — quick brief-quality check.

Paste a campaign brief; the system extracts a structured Brief, runs the
completeness rules + ambiguity detector, and shows a structured overview
table + collapsible gap list. No plan is generated here. When the user
wants to take the brief forward, the "Open in Plan from Brief" button
hands the raw text over to Page 1.

Replaces the prior Plan QA flow. The plan-content textarea has been
removed — Plan QA's audit-an-existing-plan use case is covered by Page 1's
own Run Review step against a generated plan.
"""
from __future__ import annotations

import html as _html
import os

import httpx
import streamlit as st

from ui.components.brief_table import brief_to_rows, rows_as_table_input
from ui.styles import (
    PRODUCT_NAME,
    callout,
    inject_global_css,
    key_value_table,
    render_banner,
    section_header,
    severity_pill,
    styled_error,
    top_header,
    traffic_color,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Brief QA",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_post(path: str, payload: dict | None = None, timeout: float = 90.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


for key, default in [
    ("bqa_raw_text", ""),
    ("bqa_brief_id", None),
    ("bqa_brief", None),
    ("bqa_gaps", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


render_banner(
    "Brief QA",
    "Verify a campaign brief's quality before you commit to plan generation. "
    "The system extracts a structured brief and runs completeness + ambiguity checks.",
)


# ---------------------------------------------------------------------------
# Demo-launcher hint — Get Started card C carries `_launch_demo == "C"`.
# ---------------------------------------------------------------------------

if st.session_state.get("_launch_demo") == "C" and not st.session_state.get("bqa_raw_text"):
    from pathlib import Path
    candidates = [
        "seeds/qa_demo/brief.md",
        "seeds/golden_set/brief_001.md",
    ]
    for rel in candidates:
        try:
            text = (Path(__file__).resolve().parents[2] / rel).read_text(encoding="utf-8")
            st.session_state["bqa_raw_text"] = text
            break
        except Exception:
            continue
    st.session_state["_launch_demo"] = None


# ---------------------------------------------------------------------------
# Input — full-width brief textarea
# ---------------------------------------------------------------------------

section_header("Campaign brief")
st.caption(
    "Paste markdown or plain text. The system extracts campaign name, audience, "
    "channels, budget, timeline, and constraints, then runs gap analysis."
)

raw_text = st.text_area(
    "Brief",
    height=320,
    key="bqa_raw_text",
    placeholder=(
        "Campaign Name: Q3 Demo Drive\n"
        "Business Objective: convert enterprise trial signups\n"
        "Target Audience: RevOps leaders at 1000+ employee SaaS companies\n"
        "..."
    ),
    label_visibility="collapsed",
)

run_clicked = st.button(
    "Check brief quality",
    type="primary",
    disabled=not raw_text.strip(),
    use_container_width=False,
)


if run_clicked:
    # Two-step pipeline: intake (parse + persist) then analyze (rules + ambiguity).
    with st.spinner("Extracting structured brief..."):
        code, intake = _api_post(
            "/api/v1/briefs/intake",
            {"raw_text": raw_text, "source_format": "text"},
        )
    if code >= 400:
        styled_error(
            "Could not parse the brief. Check that the API is up and the text "
            "is at least 10 characters.",
            title="Brief processing failed",
            details=str(intake),
        )
    else:
        st.session_state.bqa_brief_id = intake["brief_id"]
        st.session_state.bqa_brief = intake["brief"]
        with st.spinner("Running completeness rules + ambiguity detector..."):
            code, analyze = _api_post(
                f"/api/v1/briefs/{st.session_state.bqa_brief_id}/analyze"
            )
        if code >= 400:
            styled_error(
                "The brief was processed but gap analysis failed.",
                title="Analyze failed",
                details=str(analyze),
            )
            st.session_state.bqa_gaps = None
        else:
            st.session_state.bqa_gaps = analyze["gaps"]


# ---------------------------------------------------------------------------
# Output — structured table + collapsible gap list
# ---------------------------------------------------------------------------

if st.session_state.bqa_brief is not None:
    section_header("Brief overview")
    rows = brief_to_rows(st.session_state.bqa_brief, gaps=st.session_state.bqa_gaps)
    key_value_table(rows_as_table_input(rows))

if st.session_state.bqa_gaps is not None:
    section_header("Gap analysis")
    score = float(st.session_state.bqa_gaps.get("completeness_score", 0))
    color = traffic_color(score)
    gaps = st.session_state.bqa_gaps.get("gaps", [])
    hard = [g for g in gaps if g["severity"] == "hard"]
    soft = [g for g in gaps if g["severity"] == "soft"]

    counts_html = (
        f"<span class='pill pill-error' style='margin-right:6px'>{len(hard)} HARD</span>"
        f"<span class='pill pill-warning'>{len(soft)} SOFT</span>"
    )
    st.markdown(
        f"<div class='score-tile'>"
        f"<div class='score-tile-label'>Brief completeness</div>"
        f"<div class='score-tile-value' style='color:{color}'>"
        f"{score:.0f}<span class='score-tile-denom'> / 100</span></div>"
        f"<div class='score-tile-sub'>{counts_html}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if not gaps:
        callout(
            "✅ No hard or soft gaps remain. This brief is ready to generate a plan from.",
            kind="success",
        )
    else:
        # Same collapsible-card treatment as Page 1 — hard gaps default open,
        # soft default collapsed so the surface stays scannable.
        for g in hard + soft:
            is_hard = g["severity"] == "hard"
            sev_class = "gap-hard" if is_hard else "gap-soft"
            sev_pill_class = "error" if is_hard else "warning"
            sev_label = "HARD GAP" if is_hard else "SOFT GAP"
            field_path = _html.escape(str(g.get("field_path") or ""))
            description = _html.escape(str(g.get("description") or ""))
            source = (g.get("source") or "").lower()
            rule_id = g.get("rule_id")
            if source == "rule" and rule_id:
                source_html = (
                    f"Detected by completeness rule "
                    f"<code>{_html.escape(str(rule_id))}</code>"
                )
            elif source == "llm":
                source_html = "Detected by the AI ambiguity detector"
            else:
                source_html = f"Source: {_html.escape(source) or 'unknown'}"
            qs = g.get("suggested_questions") or []
            qs_html = ""
            if qs:
                qs_items = "".join(f"<li>{_html.escape(str(q))}</li>" for q in qs)
                qs_html = (
                    "<div class='gap-card-questions'>"
                    "<div class='gap-card-questions-title'>AI-suggested questions</div>"
                    f"<ul>{qs_items}</ul>"
                    "</div>"
                )
            open_attr = " open" if is_hard else ""
            st.markdown(
                f"<details class='gap-card {sev_class}'{open_attr}>"
                f"<summary>"
                f"{severity_pill(sev_pill_class, sev_label)}"
                f"<span class='gap-card-summary-field'>{field_path}</span>"
                f"</summary>"
                f"<div class='gap-card-body'>"
                f"<div class='gap-card-desc'>{description}</div>"
                f"<div class='gap-card-meta'>{source_html}</div>"
                f"{qs_html}"
                f"</div>"
                f"</details>",
                unsafe_allow_html=True,
            )

    # Hand-off to Plan from Brief — carries the raw text via session state so
    # Page 1's intake form is pre-populated.
    section_header("Take it forward")
    st.caption(
        "When you're satisfied with the brief, generate a multi-channel plan. "
        "The Plan from Brief workflow runs the planner, channel specialists, "
        "and copy drafters in parallel, then offers Run Review and Approve."
    )
    if st.button("Open in Plan from Brief", type="primary"):
        st.session_state["raw_text"] = st.session_state.bqa_raw_text
        try:
            st.switch_page("pages/1_Plan_from_Brief.py")
        except Exception:
            styled_error(
                "Could not switch pages automatically. Open <strong>Plan from "
                "Brief</strong> from the sidebar to continue — your brief has "
                "been saved into the form on that page.",
                title="Navigation hint",
            )
