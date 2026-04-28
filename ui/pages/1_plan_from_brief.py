"""W1 — Plan from Brief.

P3 + P4 slice: paste a brief → intake → analyze → clarify (the differentiator) →
answer questions → re-analyze and watch the gap list shrink. Planner + critic + export
land in P5..P9.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

st.set_page_config(page_title="Plan from Brief", layout="wide")

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_post(path: str, payload: dict | None = None, timeout: float = 90.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


def _severity_badge(sev: str) -> str:
    return {"hard": "🔴 hard", "soft": "🟡 soft"}.get(sev, sev)


def _completeness_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "orange"
    return "red"


# -------- Session state ---------------------------------------------------

for key, default in [
    ("brief_id", None),
    ("session_id", None),
    ("brief", None),
    ("gaps", None),
    ("questions", None),
    ("answers_cache", {}),
    ("clarified", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


st.title("W1 — Plan from Brief")
st.caption(
    "P3 + P4 live. Paste a brief → intake → analyze → clarify → answer → re-analyze. "
    "The clarification loop is the differentiator: watch the gap list shrink as the AI asks the right questions."
)

raw_text = st.text_area(
    "Paste a campaign brief (text or markdown)",
    height=280,
    placeholder="Campaign Name: ...\nBusiness Objective: ...\n...",
    key="raw_text",
)

c1, c2, c3, c4 = st.columns([1, 1, 1, 4])
with c1:
    intake_clicked = st.button("Intake", type="primary", disabled=not raw_text.strip())
with c2:
    analyze_clicked = st.button("Analyze", disabled=st.session_state.brief_id is None)
with c3:
    clarify_clicked = st.button(
        "Ask clarifying questions",
        disabled=st.session_state.brief_id is None,
        help="Differentiator: 3-5 specific, answerable questions a top campaign manager would ask.",
    )

if intake_clicked:
    with st.spinner("Extracting structured brief..."):
        code, data = _api_post("/api/v1/briefs/intake", {"raw_text": raw_text, "source_format": "text"})
    if code >= 400:
        st.error(f"Intake failed: {data}")
    else:
        st.session_state.brief_id = data["brief_id"]
        st.session_state.session_id = data["session_id"]
        st.session_state.brief = data["brief"]
        st.session_state.gaps = None
        st.session_state.questions = None
        st.session_state.answers_cache = {}
        st.session_state.clarified = False
        st.success(f"Brief ingested: {data['brief_id'][:8]}…")

if analyze_clicked and st.session_state.brief_id:
    with st.spinner("Running completeness rules + ambiguity detector..."):
        code, data = _api_post(f"/api/v1/briefs/{st.session_state.brief_id}/analyze")
    if code >= 400:
        st.error(f"Analyze failed: {data}")
    else:
        st.session_state.gaps = data["gaps"]

if clarify_clicked and st.session_state.brief_id:
    with st.spinner("Clarifier is generating questions..."):
        code, data = _api_post(f"/api/v1/briefs/{st.session_state.brief_id}/clarify")
    if code >= 400:
        st.error(f"Clarify failed: {data}")
    else:
        st.session_state.questions = data["questions"]
        st.session_state.answers_cache = {q["id"]: q.get("suggested_default") or "" for q in data["questions"]}
        st.session_state.clarified = False


# -------- Brief panel ------------------------------------------------------

if st.session_state.brief is not None:
    with st.expander("Structured brief (extracted)", expanded=False):
        st.json(st.session_state.brief)

# -------- Gap panel --------------------------------------------------------

if st.session_state.gaps is not None:
    st.divider()
    st.subheader("Gap analysis")
    score = float(st.session_state.gaps.get("completeness_score", 0))
    color = _completeness_color(score)
    st.markdown(
        f"**Completeness:** "
        f"<span style='color:{color}; font-size:2rem; font-weight:600'>{score:.0f}/100</span>",
        unsafe_allow_html=True,
    )
    gaps = st.session_state.gaps.get("gaps", [])
    if not gaps:
        st.success("No gaps detected.")
    else:
        hard = [g for g in gaps if g["severity"] == "hard"]
        soft = [g for g in gaps if g["severity"] == "soft"]
        st.write(f"**{len(hard)} hard gaps · {len(soft)} soft gaps**")
        for g in hard + soft:
            with st.expander(f"{_severity_badge(g['severity'])}  {g['field_path']} — {g['description'][:80]}"):
                st.write(f"**Description:** {g['description']}")
                st.write(
                    f"**Source:** `{g['source']}`"
                    + (f" · rule `{g['rule_id']}`" if g.get("rule_id") else "")
                )
                qs = g.get("suggested_questions") or []
                if qs:
                    st.write("**Suggested questions (raw):**")
                    for q in qs:
                        st.write(f"- {q}")

# -------- Clarification chat -----------------------------------------------

if st.session_state.questions:
    st.divider()
    st.subheader("Clarification dialog (the differentiator)")
    st.caption("Answer 3-5 specific questions; the system will re-evaluate gaps using your overrides.")

    with st.form("clarification_form"):
        for q in st.session_state.questions:
            qid = q["id"]
            label = f"**{q['prompt_text']}**"
            help_txt = f"Why: {q['rationale']}"
            qtype = q["type"]
            default = q.get("suggested_default") or ""
            if qtype == "single_select" and q.get("options"):
                options = q["options"]
                idx = options.index(default) if default in options else 0
                st.session_state.answers_cache[qid] = st.selectbox(
                    label, options, index=idx, help=help_txt, key=f"q_{qid}"
                )
            elif qtype == "multi_select" and q.get("options"):
                preset = [v.strip() for v in default.split(",") if v.strip() in q["options"]]
                vals = st.multiselect(label, q["options"], default=preset, help=help_txt, key=f"q_{qid}")
                st.session_state.answers_cache[qid] = ",".join(vals)
            elif qtype == "boolean":
                preset_b = default.lower() in ("yes", "true", "1") if default else False
                v = st.radio(label, ["Yes", "No"], index=0 if preset_b else 1, help=help_txt, key=f"q_{qid}")
                st.session_state.answers_cache[qid] = v.lower()
            else:
                st.session_state.answers_cache[qid] = st.text_input(
                    label, value=default, help=help_txt, key=f"q_{qid}"
                )

        submitted = st.form_submit_button("Submit answers", type="primary")

    if submitted:
        answers_payload = []
        for q in st.session_state.questions:
            ans = st.session_state.answers_cache.get(q["id"], "")
            if not ans:
                continue
            answers_payload.append(
                {
                    "question_id": q["id"],
                    "field_path": q["field_path"],
                    "answer": ans,
                    "reason": "user_clarification",
                }
            )
        if not answers_payload:
            st.warning("Provide at least one answer.")
        else:
            with st.spinner("Applying overrides..."):
                code, data = _api_post(
                    f"/api/v1/briefs/{st.session_state.brief_id}/overrides",
                    {"answers": answers_payload},
                )
            if code >= 400:
                st.error(f"Override apply failed: {data}")
            else:
                st.session_state.brief = data["brief"]
                st.session_state.clarified = True
                st.success(f"{data['overrides_applied']} override(s) applied. Click Analyze to see the new gap list.")

if st.session_state.clarified and not st.session_state.questions:
    st.info("Clarification complete. Re-run analyze to see the updated gap list.")


# -------- P5: Plan generation ---------------------------------------------

if "plan" not in st.session_state:
    st.session_state.plan = None
    st.session_state.copy_drafts = {}

st.divider()
st.subheader("Generate execution plan (P5)")
st.caption(
    "Planner produces a campaign skeleton; Channel Specialists fan out (parallel); "
    "Copy Drafters produce per-channel copy with brand voice scores; Timeline synthesizes a "
    "dependency-aware schedule."
)
plan_clicked = st.button(
    "Generate plan",
    type="primary",
    disabled=st.session_state.brief_id is None,
    help="Runs planner + channel specialists + copy drafter + timeline synthesizer.",
)

if plan_clicked and st.session_state.brief_id:
    with st.spinner("Generating execution plan (planner → channel specialists → copy drafts → timeline)..."):
        code, data = _api_post(f"/api/v1/briefs/{st.session_state.brief_id}/plan", {}, timeout=180.0)
    if code >= 400:
        st.error(f"Plan generation failed: {data}")
    else:
        st.session_state.plan = data["plan"]
        st.session_state.copy_drafts = data.get("copy_drafts") or {}
        st.success(f"Plan generated: {data['plan_id'][:8]}…")


if st.session_state.plan:
    plan = st.session_state.plan
    st.markdown(f"### {plan['campaign_identity']['name']}")
    st.caption(plan.get("audience_summary", ""))

    # Resolved objectives
    if plan.get("resolved_objectives"):
        with st.expander("Resolved objectives", expanded=True):
            for obj in plan["resolved_objectives"]:
                target = obj.get("target")
                baseline = obj.get("baseline")
                line = f"**{obj['objective']}**"
                if target is not None:
                    line += f" — target: {target}" + (f" (baseline {baseline})" if baseline is not None else "")
                if obj.get("addressed_by_channels"):
                    line += " · channels: " + ", ".join(obj["addressed_by_channels"])
                st.markdown(line)

    # Channels with copy drafts
    st.markdown("#### Channels")
    drafts = st.session_state.copy_drafts or {}
    cols = st.columns(min(len(plan["channels"]), 3) or 1)
    for i, ch in enumerate(plan["channels"]):
        with cols[i % len(cols)]:
            st.markdown(f"**{ch['channel_name']}**")
            st.caption(f"Owner: {ch['owner_placeholder']}  ·  CTA: _{ch['cta']}_")
            if ch.get("notes"):
                st.write(ch["notes"])
            draft = drafts.get(str(ch["id"]))
            if draft:
                vs = float(draft.get("voice_score", 0))
                color = _completeness_color(vs)
                st.markdown(
                    f"Voice score: <span style='color:{color}; font-weight:600'>{vs:.0f}/100</span>"
                    f"  ·  angle: _{draft.get('angle', '?')}_",
                    unsafe_allow_html=True,
                )
                st.text_area(
                    f"copy_{ch['id']}",
                    value=draft.get("body", ""),
                    height=180,
                    label_visibility="collapsed",
                    disabled=True,
                )
            if ch.get("asset_requirements"):
                st.caption("Assets: " + ", ".join(ch["asset_requirements"]))

    # Timeline (Gantt-ish)
    st.markdown("#### Timeline")
    weeks = plan.get("timeline", {}).get("weeks") or []
    if weeks:
        for w in weeks:
            with st.container():
                header = f"**Week {w['week_number']}**"
                if w.get("milestones"):
                    header += " — " + " · ".join(w["milestones"])
                st.markdown(header)
                acts = w.get("channel_activities") or {}
                if acts:
                    for ch_name, items in acts.items():
                        if items:
                            st.caption(f"  {ch_name}: {' / '.join(items)}")
    deps = plan.get("timeline", {}).get("dependencies") or []
    if deps:
        with st.expander("Dependencies"):
            for d in deps:
                st.markdown(f"- {d}")

    # QA + metrics
    with st.expander("QA checkpoints + success metrics"):
        for q in plan.get("qa_checkpoints", []):
            wk = q.get("occurs_at_week")
            st.markdown(f"- **{q['name']}**" + (f" (week {wk})" if wk else "") + f" — {q['description']}")
        st.markdown("---")
        for m in plan.get("success_metric_bindings", []):
            st.markdown(
                f"- **{m['metric_name']}** — {m['measurement_approach']}"
                + (f" · owner: {m['owner_placeholder']}" if m.get("owner_placeholder") else "")
            )

    # ---- P6: Review + Approval ------------------------------------------

    if "review" not in st.session_state:
        st.session_state.review = None
        st.session_state.ledger = None
        st.session_state.plan_status = plan.get("status", "draft")

    st.divider()
    st.subheader("Review + Approval (P6)")
    st.caption(
        "Critic + deterministic governance scanners produce a severity-ranked ValidationReport. "
        "Assumption Ledger walks every choice in the plan with citations."
    )
    rc1, rc2, rc3 = st.columns([1, 1, 1])
    with rc1:
        review_clicked = st.button("Run review", type="primary")
    with rc2:
        approve_clicked = st.button("Approve plan", disabled=st.session_state.review is None)
    with rc3:
        reject_clicked = st.button("Reject plan", disabled=st.session_state.review is None)

    plan_id = plan.get("id")
    if review_clicked and plan_id:
        with st.spinner("Critic + governance + ledger composer running..."):
            code, data = _api_post(f"/api/v1/plans/{plan_id}/review", {}, timeout=180.0)
        if code >= 400:
            st.error(f"Review failed: {data}")
        else:
            st.session_state.review = data["validation_report"]
            st.session_state.ledger = data["ledger"]
            st.session_state.plan_status = "in_review" if data.get("blocking") else "draft"

    if approve_clicked and plan_id:
        code, data = _api_post(f"/api/v1/plans/{plan_id}/approve", {})
        if code >= 400:
            st.error(f"Approve failed: {data}")
        else:
            st.session_state.plan_status = data["status"]
            st.success("Plan approved")

    if reject_clicked and plan_id:
        code, data = _api_post(f"/api/v1/plans/{plan_id}/reject", {})
        if code >= 400:
            st.error(f"Reject failed: {data}")
        else:
            st.session_state.plan_status = data["status"]
            st.warning("Plan rejected")

    st.caption(f"Status: **{st.session_state.plan_status}**")

    if st.session_state.review:
        report = st.session_state.review
        align = float(report.get("alignment_score", 0))
        color = _completeness_color(align)
        st.markdown(
            f"**Alignment:** <span style='color:{color}; font-size:1.5rem; font-weight:600'>{align:.0f}/100</span>",
            unsafe_allow_html=True,
        )
        sev_emoji = {"info": "🟢", "warning": "🟡", "error": "🔴", "blocker": "⛔"}
        for f in report.get("findings", []):
            sev = f["severity"]
            with st.expander(
                f"{sev_emoji.get(sev, '•')}  {sev.upper()} · {f['category']} — {f['description'][:80]}"
            ):
                st.markdown(f"**Description:** {f['description']}")
                st.markdown(f"**Brief passage:** _{f['brief_passage']}_")
                st.markdown(f"**Plan section:** `{f['plan_section_ref']}`")
                st.markdown(f"**Suggested fix:** {f['suggested_fix']}")
        if not report.get("findings"):
            st.success("Critic + governance scanners found no issues.")

    if st.session_state.ledger:
        ledger = st.session_state.ledger
        entries = ledger.get("entries") or []
        with st.expander(f"Assumption Ledger ({len(entries)} entries)"):
            for e in entries:
                conf_pct = int(round(float(e.get("confidence", 0)) * 100))
                st.markdown(
                    f"- **{e['field_path']}** _(by {e['created_by_agent']}, {e['basis']}, {conf_pct}% conf.)_  \n"
                    f"  {e['assumption_text']}  \n"
                    f"  _cite: {e['citation']}_"
                )
