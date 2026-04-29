"""W2 — Standalone QA on an existing brief + plan pair.

Paste a brief and a plan JSON, run the Critic + governance scanners, see a severity-ranked
ValidationReport with citations and suggested fixes.

The "Load Sample Brief A + mismatched plan" button fills both textareas with the demo pair
from `seeds/qa_demo/` — an enterprise brief paired with an SMB-tone plan, designed to make
the critic emit coverage + audience + compliance findings the audience can read at a glance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import streamlit as st

from ui.styles import inject_global_css, render_banner, severity_pill, styled_error


st.set_page_config(page_title="Axion · QA Existing Plan", layout="wide")
inject_global_css()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QA_DEMO_DIR = _PROJECT_ROOT / "seeds" / "qa_demo"


def _api_post(path: str, payload: dict | None = None, timeout: float = 120.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


def _alignment_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "orange"
    return "red"


SEV_EMOJI = {"info": "🟢", "warning": "🟡", "error": "🔴", "blocker": "⛔"}
SEV_RANK = {"blocker": 0, "error": 1, "warning": 2, "info": 3}


# -------- Session state ---------------------------------------------------

for key, default in [
    ("qa_brief_text", ""),
    ("qa_plan_json", ""),
    ("qa_report", None),
    ("qa_blocking", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


render_banner(
    "W2 · Standalone QA",
    "Paste a brief and a plan JSON. The Critic + deterministic governance scanners run "
    "exactly the same way they do inside W1's revision loop — different entry point, same agent.",
    tags=["W2", "QA"],
)

# If the user came from the demo launcher with letter='C', auto-load the demo pair.
if st.session_state.get("_launch_demo") == "C" and not st.session_state.get("qa_brief_text"):
    try:
        with httpx.Client(timeout=3.0) as _c:
            _r = _c.get(f"{API_BASE}/api/v1/demo/payload?key=demo:c:payload")
            if _r.status_code == 200:
                _p = _r.json()
                st.session_state["qa_brief_text"] = _p.get("brief_text", "")
                import json as _j
                st.session_state["qa_plan_json"] = _j.dumps(_p.get("plan_json", {}), indent=2)
    except Exception:
        pass
    st.session_state["_launch_demo"] = None


def _load_demo() -> tuple[str, str]:
    brief_path = _QA_DEMO_DIR / "brief.md"
    plan_path = _QA_DEMO_DIR / "plan.json"
    brief_text = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    return brief_text, plan_text


load_clicked = st.button("Load Sample Brief A + mismatched plan", help="Pre-stages the W2 demo pair.")
if load_clicked:
    brief_text, plan_text = _load_demo()
    st.session_state.qa_brief_text = brief_text
    st.session_state.qa_plan_json = plan_text
    st.session_state.qa_report = None
    st.session_state.qa_blocking = False

c1, c2 = st.columns(2)
with c1:
    st.subheader("Brief")
    brief_text = st.text_area(
        "Brief (text or markdown)",
        height=420,
        key="qa_brief_text",
        placeholder="# Campaign Name…",
    )
with c2:
    st.subheader("Plan JSON")
    plan_text = st.text_area(
        "ExecutionPlan JSON",
        height=420,
        key="qa_plan_json",
        placeholder='{"id": "…", "campaign_identity": {…}, "channels": [...]}',
    )

run_clicked = st.button(
    "Run QA",
    type="primary",
    disabled=not (st.session_state.qa_brief_text.strip() and st.session_state.qa_plan_json.strip()),
)

if run_clicked:
    try:
        plan_obj = json.loads(st.session_state.qa_plan_json)
    except json.JSONDecodeError as exc:
        styled_error(str(exc), title="Plan JSON is not valid JSON")
    else:
        with st.spinner("Running Critic + governance scanners…"):
            code, data = _api_post(
                "/api/v1/qa",
                {"brief_text": st.session_state.qa_brief_text, "plan_json": plan_obj},
            )
        if code >= 400:
            styled_error(f"({code}) <code>{data}</code>", title="QA failed")
        else:
            st.session_state.qa_report = data["validation_report"]
            st.session_state.qa_blocking = bool(data.get("blocking", False))


# -------- Render the report ----------------------------------------------

if st.session_state.qa_report:
    report = st.session_state.qa_report
    align = float(report.get("alignment_score", 0))
    color = _alignment_color(align)
    findings = sorted(
        report.get("findings", []),
        key=lambda f: (SEV_RANK.get(f.get("severity", "info"), 99)),
    )

    st.markdown("---")
    headline_col, count_col = st.columns([2, 1])
    with headline_col:
        st.markdown(
            f"**Alignment score:** <span style='color:{color}; font-size:2rem; font-weight:600'>{align:.0f}/100</span>",
            unsafe_allow_html=True,
        )
    with count_col:
        sev_counts = {k: 0 for k in SEV_EMOJI}
        for f in findings:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
        chips = " · ".join(f"{SEV_EMOJI[k]} {sev_counts[k]}" for k in ["blocker", "error", "warning", "info"])
        st.markdown(f"**Findings:** {chips}")

    if st.session_state.qa_blocking:
        st.markdown(
            severity_pill("blocker", "DO NOT SHIP — blocker / error findings present"),
            unsafe_allow_html=True,
        )
    elif not findings:
        st.success("Critic + governance scanners found no issues.")

    # Top Issues panel — first 3 by severity rank.
    top = findings[:3]
    if top:
        st.markdown("### Top Issues")
        for f in top:
            sev = f["severity"]
            st.markdown(
                f"{SEV_EMOJI.get(sev, '•')} **{sev.upper()}** · _{f['category']}_ — {f['description']}"
            )

    st.markdown("### All Findings")
    for f in findings:
        sev = f["severity"]
        with st.expander(
            f"{SEV_EMOJI.get(sev, '•')}  {sev.upper()} · {f['category']} — {f['description'][:80]}"
        ):
            st.markdown(f"**Description:** {f['description']}")
            st.markdown(f"**Brief passage:** _{f['brief_passage']}_")
            st.markdown(f"**Plan section:** `{f['plan_section_ref']}`")
            st.markdown(f"**Suggested fix:** {f['suggested_fix']}")

    st.download_button(
        "Download report JSON",
        data=json.dumps(report, indent=2, default=str),
        file_name=f"validation_report_{report.get('id', 'qa')}.json",
        mime="application/json",
    )
