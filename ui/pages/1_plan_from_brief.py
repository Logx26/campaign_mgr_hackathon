"""Plan from Brief — the headline workflow.

Flow: paste brief → process → find gaps → suggest questions → submit answers
      → re-find gaps → generate plan → run review → approve / regenerate / reject.

P11 Iteration 2 changes:
  - Lumeo light theme + structured brief table (no raw JSON).
  - Three-score legend so completeness / voice / alignment aren't conflated.
  - Regenerate plan button after review to act on Critic findings.
  - Approve-with-blockers requires explicit acknowledgment.
  - Auto-scroll between sections on action completion.
"""
from __future__ import annotations

import html as _html
import json as _json
import os
import re as _re
from pathlib import Path

import httpx
import streamlit as st
import streamlit.components.v1 as _components

from ui.components.brief_table import brief_to_rows, rows_as_table_input
from ui.styles import (
    PRODUCT_NAME,
    callout,
    inject_global_css,
    key_value_table,
    render_banner_with_legend,
    scroll_to,
    scrub_override_prefix,
    section_header,
    severity_pill,
    step_rail,
    styled_error,
    top_header,
    traffic_color,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Plan from Brief",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
SEVERITY_RANK = {"blocker": 0, "error": 1, "warning": 2, "info": 3}


# ---------------------------------------------------------------------------
# Copy preview helpers
# ---------------------------------------------------------------------------

# Recognized labeled-line prefixes — bold-styled in the rendered preview so
# Subject/Preheader/Touch N read as labeled rows instead of plain prose.
_COPY_LABEL_RE = _re.compile(
    r"^(Subject|Preheader|Touch\s*\d+|For\s+[^:\n]{1,40}|CTA|Follow[- ]up\s*\d*|Day\s*\d+):\s*(.*)$",
    flags=_re.IGNORECASE,
)


def _channel_icon(name: str) -> str:
    """Pick a single emoji for a channel name. Falls back to a paperclip."""
    n = (name or "").lower()
    if "email" in n:
        return "✉️"
    if "linkedin" in n:
        return "💼"
    if "sdr" in n or "outreach" in n:
        return "📞"
    if "search" in n or "paid" in n:
        return "🎯"
    if "landing" in n:
        return "🪂"
    if "event" in n:
        return "📅"
    return "📎"


def _format_copy_body_html(body: str) -> str:
    """Convert plain-text copy body into formatted HTML.

    Lines whose content matches `Subject:`, `Preheader:`, `Touch N:`, `For X:`,
    `CTA:`, `Follow-up N:`, `Day N:` get a bold accent-colored label; the
    remaining text becomes the row body. Blank lines split paragraphs."""
    paragraphs: list[tuple[str, str | None]] = []  # (text, label)
    current: list[str] = []
    for raw in (body or "").splitlines():
        stripped = raw.rstrip()
        if not stripped:
            if current:
                paragraphs.append((" ".join(current), None))
                current = []
            continue
        m = _COPY_LABEL_RE.match(stripped)
        if m:
            if current:
                paragraphs.append((" ".join(current), None))
                current = []
            paragraphs.append((m.group(2).strip(), m.group(1).strip()))
        else:
            current.append(stripped)
    if current:
        paragraphs.append((" ".join(current), None))

    parts: list[str] = []
    for text, label in paragraphs:
        if label:
            parts.append(
                f"<p><span class='copy-label'>{_html.escape(label)}:</span> "
                f"{_html.escape(text)}</p>"
            )
        else:
            parts.append(f"<p>{_html.escape(text)}</p>")
    return "\n".join(parts) or "<p style='color:#94A3B8'>(no copy)</p>"


def _render_copy_preview(channel_name: str, body: str) -> None:
    """Render the copy preview as a self-contained components.v1 iframe.

    The iframe holds: (1) a header bar with a channel icon + Copy button,
    (2) a formatted body with bold-labeled lines, (3) a hidden textarea
    holding the plain-text body, (4) a click handler that copies the
    plain text to the user's clipboard via navigator.clipboard. Each
    preview lives in its own iframe so multiple channel previews coexist
    without ID collisions."""
    sanitized = _re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", body or ""
    )
    formatted = _format_copy_body_html(sanitized)
    icon = _channel_icon(channel_name)
    raw_json = _json.dumps(sanitized)  # safe to embed in JS
    html_doc = f"""
<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin:0; padding:0; background:transparent;
    font-family: 'Inter','Segoe UI',-apple-system,system-ui,sans-serif;
    color:#0F172A; }}
  .frame {{ background:#FFFFFF; border:1px solid #E2E6EF; border-radius:10px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.05); overflow:hidden; }}
  .head {{ background: linear-gradient(180deg,#F8FAFF 0%,#EEF2FF 100%);
    border-bottom:1px solid #E2E6EF; padding:7px 12px;
    display:flex; align-items:center; justify-content:space-between; gap:10px; }}
  .head-left {{ display:inline-flex; align-items:center; gap:8px;
    color:#4F46E5; font-size:0.74rem; font-weight:700;
    text-transform:uppercase; letter-spacing:0.08em; }}
  .icon {{ font-size:1rem; line-height:1; }}
  .copy-btn {{ background:transparent; border:1px solid rgba(79,70,229,0.32);
    color:#4F46E5; font-size:0.72rem; font-weight:700; padding:3px 12px;
    border-radius:999px; cursor:pointer; transition: all 0.15s ease;
    font-family: inherit; letter-spacing: 0.04em; }}
  .copy-btn:hover {{ background:rgba(79,70,229,0.10); }}
  .copy-btn.copied {{ background:rgba(22,163,74,0.10);
    border-color:rgba(22,163,74,0.40); color:#16A34A; }}
  .body {{ padding:12px 16px; max-height:240px; overflow-y:auto;
    font-size:0.88rem; line-height:1.6; }}
  .body p {{ margin: 0 0 8px 0; }}
  .body p:last-child {{ margin-bottom:0; }}
  .copy-label {{ color:#4F46E5; font-weight:700; margin-right:2px; }}
  .raw {{ position:absolute; left:-9999px; top:-9999px; }}
</style></head><body>
<div class="frame">
  <div class="head">
    <div class="head-left">
      <span class="icon">{icon}</span>
      <span>Copy preview · {_html.escape(channel_name)}</span>
    </div>
    <button class="copy-btn" id="copy-btn" type="button">📋 Copy</button>
  </div>
  <div class="body">{formatted}</div>
</div>
<textarea class="raw" id="raw-text" readonly>{_html.escape(sanitized)}</textarea>
<script>
  (function() {{
    var btn = document.getElementById('copy-btn');
    var raw = {raw_json};
    if (!btn) return;
    btn.addEventListener('click', function() {{
      function flash() {{
        btn.classList.add('copied');
        btn.innerText = '✓ Copied';
        setTimeout(function() {{
          btn.classList.remove('copied');
          btn.innerText = '📋 Copy';
        }}, 1500);
      }}
      try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(raw).then(flash, function() {{
            var ta = document.getElementById('raw-text');
            ta.style.left = '0'; ta.style.top = '0'; ta.select();
            document.execCommand('copy');
            ta.style.left = '-9999px'; ta.style.top = '-9999px';
            flash();
          }});
        }} else {{
          var ta = document.getElementById('raw-text');
          ta.style.left = '0'; ta.style.top = '0'; ta.select();
          document.execCommand('copy');
          ta.style.left = '-9999px'; ta.style.top = '-9999px';
          flash();
        }}
      }} catch (e) {{ /* clipboard blocked — silent */ }}
    }});
  }})();
</script>
</body></html>
"""
    _components.html(html_doc, height=320, scrolling=False)


def _api_post(path: str, payload: dict | None = None, timeout: float = 90.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


for key, default in [
    ("brief_id", None),
    ("session_id", None),
    ("brief", None),
    ("gaps", None),
    ("questions", None),
    ("answers_cache", {}),
    ("clarified", False),
    ("plan", None),
    ("copy_drafts", {}),
    ("review", None),
    ("ledger", None),
    ("plan_status", "draft"),
    ("approve_ack", False),
    ("scroll_target", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---- Banner + score legend ------------------------------------------------

render_banner_with_legend(
    "Plan from Brief",
    "Paste a campaign brief, resolve gaps with the AI, and ship a reviewable plan in under 90 seconds.",
)


# ---- Demo-launcher hint ---------------------------------------------------

# Card B's brief has the same content as `seeds/exemplar_briefs/b2b_saas_q3_
# enterprise.md` but in paragraph form, so the user sees that the textarea
# accepts free-flowing prose, not just a labeled-section template. Card A
# still loads its structured markdown brief — that one shows the parser
# coping with the canonical template format.
_DEMO_B_PARAGRAPH = (
    "We're running a Q3 Enterprise Trial-to-Paid Push. The primary objective "
    "is to convert 200 enterprise trial accounts at companies with 1000+ "
    "employees to paid contracts before the end of Q3, with a secondary goal "
    "of generating 50 new enterprise demo requests from net-new prospects. "
    "Target audience is trial users at 1000+ employee companies in technology, "
    "financial services, and professional services — specifically decision-"
    "makers like VPs of Operations, Directors of Revenue Operations, and "
    "Chief Marketing Officers. Our key message: teams managing revenue "
    "operations at scale are leaving hours of manual work on the table; our "
    "platform eliminates the reporting lag between data capture and decision "
    "so revenue teams act on what's happening now, not what happened last "
    "Tuesday. We want to be on Email, LinkedIn, social (we haven't decided "
    "which platforms exactly), and sales outreach. Budget hasn't been "
    "finalized yet. Campaign should go live by July 1, with all assets "
    "locked by June 20. Success metrics: trial-to-paid conversion rate "
    "(baseline 14%, target 22%), and 50 demo requests from net-new "
    "enterprise accounts in 6 weeks. Brand constraints: don't reference "
    "competitors by name, all time-savings claims need customer quotes or "
    "case studies, tone should be confident and direct (never aggressive), "
    "and avoid jargon like \"AI-powered\" without a concrete example of "
    "what the AI actually does."
)

if st.session_state.get("_launch_demo") in {"A", "B"} and not st.session_state.get("raw_text"):
    if st.session_state["_launch_demo"] == "A":
        try:
            st.session_state["raw_text"] = (
                Path(__file__).resolve().parents[2] / "seeds/golden_set/brief_002.md"
            ).read_text(encoding="utf-8")
        except Exception:
            pass
    else:  # "B" — paragraph-form prose, same content as the exemplar brief
        st.session_state["raw_text"] = _DEMO_B_PARAGRAPH
    st.session_state["_launch_demo"] = None


# ---- Step rail ------------------------------------------------------------


def _step_state() -> list[str]:
    out = ["pending"] * 5
    if st.session_state.brief_id is None:
        out[0] = "current"
        return out
    out[0] = "done"
    if st.session_state.gaps is None:
        out[1] = "current"
        return out
    out[1] = "done"
    if st.session_state.questions and not st.session_state.clarified:
        out[2] = "current"
        return out
    if st.session_state.questions or st.session_state.clarified:
        out[2] = "done"
    if st.session_state.plan is None:
        out[3] = "current"
        return out
    out[3] = "done"
    out[4] = "current" if st.session_state.review is None else "done"
    return out


_states = _step_state()
_labels = ["Brief", "Analyze", "Clarify", "Plan", "Review"]
step_rail(list(zip(_labels, _states)))


# ---- Section 1 — Brief input ---------------------------------------------

st.markdown("<a id='brief-anchor'></a>", unsafe_allow_html=True)
section_header("Campaign brief")
st.caption(
    "Paste markdown or plain text. The system will extract campaign name, audience, channels, "
    "budget, timeline, and constraints."
)

raw_text = st.text_area(
    "Brief",
    height=260,
    placeholder=(
        "Campaign Name: Q3 Demo Drive\n"
        "Business Objective: convert enterprise trial signups\n"
        "Target Audience: RevOps leaders at 1000+ employee SaaS companies\n"
        "..."
    ),
    key="raw_text",
    label_visibility="collapsed",
)

bc1, bc2, bc3 = st.columns(3, gap="small")
with bc1:
    intake_clicked = st.button(
        "Process brief", type="primary",
        disabled=not raw_text.strip(),
        use_container_width=True,
    )
with bc2:
    analyze_clicked = st.button(
        "Run analysis",
        disabled=st.session_state.brief_id is None,
        use_container_width=True,
        help="Runs the completeness rules + ambiguity detector against the brief.",
    )
with bc3:
    clarify_clicked = st.button(
        "Ask AI to clarify",
        disabled=st.session_state.brief_id is None,
        use_container_width=True,
        help="The AI asks 3–5 typed questions to fill the gaps it detected.",
    )


# ---- Action handlers -----------------------------------------------------

if intake_clicked:
    with st.spinner("Extracting structured brief..."):
        code, data = _api_post(
            "/api/v1/briefs/intake", {"raw_text": raw_text, "source_format": "text"}
        )
    if code >= 400:
        styled_error(
            "Could not parse the brief. Check that the API is up and the text is at least 10 characters.",
            title="Brief processing failed",
            details=str(data),
        )
    else:
        st.session_state.brief_id = data["brief_id"]
        st.session_state.session_id = data["session_id"]
        st.session_state.brief = data["brief"]
        st.session_state.gaps = None
        st.session_state.questions = None
        st.session_state.answers_cache = {}
        st.session_state.clarified = False
        st.session_state.plan = None
        st.session_state.review = None
        try:
            st.toast("Brief processed.")
        except Exception:
            pass
        # Force a clean re-render so the brief overview + step rail reflect the
        # new state on the same click — no second click required.
        st.rerun()

if analyze_clicked and st.session_state.brief_id:
    with st.spinner("Running completeness rules + ambiguity detector..."):
        code, data = _api_post(f"/api/v1/briefs/{st.session_state.brief_id}/analyze")
    if code >= 400:
        styled_error("Could not run analysis.", title="Analyze failed", details=str(data))
    else:
        st.session_state.gaps = data["gaps"]
        st.session_state.scroll_target = "gap-anchor"
        st.rerun()

if clarify_clicked and st.session_state.brief_id:
    with st.spinner("AI is generating clarifying questions..."):
        code, data = _api_post(f"/api/v1/briefs/{st.session_state.brief_id}/clarify")
    if code >= 400:
        styled_error("Could not generate clarifying questions.", title="Clarify failed", details=str(data))
    else:
        st.session_state.questions = data["questions"]
        st.session_state.answers_cache = {
            q["id"]: q.get("suggested_default") or "" for q in data["questions"]
        }
        st.session_state.clarified = False
        st.session_state.scroll_target = "clarify-anchor"
        st.rerun()


# ---- Section 2 — Brief overview (table) ----------------------------------

if st.session_state.brief is not None:
    st.markdown(
        "<a id='analysis-anchor'></a><a id='brief-overview-anchor'></a>",
        unsafe_allow_html=True,
    )
    section_header("Brief overview")
    rows = brief_to_rows(st.session_state.brief, gaps=st.session_state.gaps)
    key_value_table(rows_as_table_input(rows))


# ---- Section 3 — Gap analysis -------------------------------------------

if st.session_state.gaps is not None:
    st.markdown("<a id='gap-anchor'></a>", unsafe_allow_html=True)
    section_header("Gap analysis")
    score = float(st.session_state.gaps.get("completeness_score", 0))
    color = traffic_color(score)
    gaps = st.session_state.gaps.get("gaps", [])
    hard = [g for g in gaps if g["severity"] == "hard"]
    soft = [g for g in gaps if g["severity"] == "soft"]

    # Headline tile + counts.
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
        callout("✅ No hard or soft gaps remain. You can generate the plan.", kind="success")
    else:
        # Render each gap as a collapsible <details>. Hard gaps default open
        # (they block plan quality and need attention); soft gaps default
        # collapsed so the page isn't dominated by minor ambiguities.
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


# ---- Section 4 — Clarification dialog ------------------------------------

if st.session_state.questions:
    st.markdown("<a id='clarify-anchor'></a>", unsafe_allow_html=True)
    section_header("Clarification questions")
    st.caption(
        "Answer 3–5 specific questions; the system reapplies your answers to the brief and "
        "re-runs gap analysis. Free-text answers that target list-typed fields are recorded as "
        "audit lines on mandatory inclusions."
    )

    with st.form("clarification_form"):
        for q in st.session_state.questions:
            qid = q["id"]
            label = f"**{scrub_override_prefix(q['prompt_text'])}**"
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
            callout("Provide at least one answer before submitting.", kind="warning")
        else:
            with st.spinner("Applying overrides..."):
                code, data = _api_post(
                    f"/api/v1/briefs/{st.session_state.brief_id}/overrides",
                    {"answers": answers_payload},
                )
            if code == 422:
                detail = data.get("detail") or {}
                paths = ", ".join(detail.get("field_paths") or [])
                styled_error(
                    f"Some answers couldn't be applied to their target fields: <code>{paths}</code>. "
                    "Your inputs were saved as audit lines on mandatory inclusions — try rephrasing or "
                    "skip the affected questions.",
                    title="Some overrides could not be applied",
                    details=str(data),
                )
            elif code >= 400:
                styled_error(
                    "Could not apply your answers.",
                    title="Override apply failed",
                    details=str(data),
                )
            else:
                st.session_state.brief = data["brief"]
                st.session_state.clarified = True
                with st.spinner("Re-running gap analysis with your answers applied..."):
                    code, gdata = _api_post(
                        f"/api/v1/briefs/{st.session_state.brief_id}/analyze"
                    )
                if code < 400:
                    st.session_state.gaps = gdata["gaps"]
                # After clarify Submit we want the user back on the Brief Overview
                # so they can see the updated structured brief + new completeness
                # score side-by-side, not stuck on the form they just submitted.
                st.session_state.scroll_target = "brief-overview-anchor"
                callout(
                    f"<strong>{data['overrides_applied']} answer(s) applied.</strong> "
                    "Brief updated — scroll up to see the refreshed overview and gap list.",
                    kind="success",
                )
                st.rerun()

if st.session_state.clarified and not st.session_state.questions:
    callout("Clarification complete. Generate the plan when you're ready.", kind="info")


# ---- Section 5 — Plan generation -----------------------------------------

st.markdown("<a id='plan-anchor'></a>", unsafe_allow_html=True)
section_header("Generate the plan")
st.caption(
    "Planner produces a campaign skeleton; channel specialists fan out in parallel; copy drafters "
    "produce per-channel copy with brand voice scores; the timeline synthesizer schedules the work "
    "with cross-channel dependencies."
)

plan_btn_label = "Regenerate plan" if st.session_state.plan else "Generate plan"
plan_clicked = st.button(
    plan_btn_label,
    type="primary",
    disabled=st.session_state.brief_id is None,
    help="Re-running plan generation produces a different plan and clears any prior review.",
)

if plan_clicked and st.session_state.brief_id:
    with st.spinner("Generating execution plan..."):
        code, data = _api_post(
            f"/api/v1/briefs/{st.session_state.brief_id}/plan", {}, timeout=180.0
        )
    if code >= 400:
        styled_error("Plan generation failed.", title="Plan generation failed", details=str(data))
    else:
        st.session_state.plan = data["plan"]
        st.session_state.copy_drafts = data.get("copy_drafts") or {}
        st.session_state.review = None
        st.session_state.ledger = None
        st.session_state.plan_status = data["plan"].get("status", "draft")
        st.session_state.approve_ack = False
        st.session_state.scroll_target = "plan-anchor"
        st.rerun()


if st.session_state.plan:
    plan = st.session_state.plan
    st.markdown(
        f"<h3 style='margin-top:8px'>{_html.escape(plan['campaign_identity']['name'])}</h3>",
        unsafe_allow_html=True,
    )
    if plan.get("audience_summary"):
        st.caption(plan["audience_summary"])

    brief_for_render = st.session_state.brief or {}
    budget_block = (brief_for_render or {}).get("budget") if isinstance(brief_for_render, dict) else None
    budget_total = (budget_block or {}).get("total") if isinstance(budget_block, dict) else None
    if budget_total in (None, "", 0):
        callout(
            "<strong>Budget:</strong> Not specified in the brief — assuming a lean test budget. "
            "Add a total in the brief if you want budget-bound recommendations.",
            kind="warning",
        )

    if plan.get("resolved_objectives"):
        with st.expander("Resolved objectives", expanded=True):
            obj_rows = []
            for obj in plan["resolved_objectives"]:
                target = obj.get("target")
                baseline = obj.get("baseline")
                metric = obj.get("target_metric") or "—"
                if target is not None and baseline is not None:
                    arrow = f"{baseline} → {target}"
                elif target is not None:
                    arrow = f"target {target}"
                else:
                    arrow = "—"
                channels = ", ".join(obj.get("addressed_by_channels") or []) or "—"
                obj_rows.append((obj["objective"], f"{metric} · {arrow}", channels))
            obj_html_rows = "".join(
                f"<tr><td class='kv-field'>{_html.escape(str(a))}</td>"
                f"<td class='kv-value'>{_html.escape(str(b))}</td>"
                f"<td class='kv-value'>{_html.escape(str(c))}</td></tr>"
                for a, b, c in obj_rows
            )
            st.markdown(
                "<table class='lumeo-kv'>"
                "<thead><tr><th>Objective</th><th>Metric · target</th><th>Channels</th></tr></thead>"
                f"<tbody>{obj_html_rows}</tbody></table>",
                unsafe_allow_html=True,
            )

    section_header("Channels")
    drafts = st.session_state.copy_drafts or {}
    cols = st.columns(min(len(plan["channels"]), 3) or 1)
    for i, ch in enumerate(plan["channels"]):
        with cols[i % len(cols)]:
            owner = (ch.get("owner_placeholder") or "").strip() or "—"
            cta = (ch.get("cta") or "").strip() or "—"
            st.markdown(
                "<div class='lumeo-card'>"
                f"<div class='lumeo-overline' style='display:block; margin-bottom:6px'>"
                f"{_html.escape(str(ch['channel_name']).upper())}</div>",
                unsafe_allow_html=True,
            )

            draft = drafts.get(str(ch["id"]))
            voice_html = ""
            if draft:
                breakdown = draft.get("voice_score_breakdown") or {}
                fp_missing = breakdown.get("fingerprint_available") == 0.0
                scoring_failed = breakdown.get("scoring_failed") == 1.0
                angle = (draft.get("angle") or "outcome-led").strip() or "outcome-led"
                if fp_missing:
                    voice_html = (
                        f"<span style='color:var(--warning); font-weight:600'>"
                        f"🟠 voice fingerprint unavailable</span> · angle: <em>{_html.escape(angle)}</em>"
                    )
                elif scoring_failed:
                    voice_html = (
                        f"<span style='color:var(--warning); font-weight:600'>"
                        f"🟠 voice scoring failed</span> · angle: <em>{_html.escape(angle)}</em>"
                    )
                else:
                    vs = float(draft.get("voice_score", 0))
                    color = traffic_color(vs)
                    voice_html = (
                        f"Voice <span style='color:{color}; font-weight:700'>{vs:.0f}/100</span> "
                        f"<span class='lumeo-caption'>· angle: <em>{_html.escape(angle)}</em></span>"
                    )
            st.markdown(voice_html, unsafe_allow_html=True)

            meta_rows: list = [("CTA", cta), ("Owner", owner)]
            if ch.get("asset_requirements"):
                meta_rows.append(("Asset count", str(len(ch["asset_requirements"]))))
            key_value_table(meta_rows, columns=("Field", "Value", ""), status_col=False)

            if draft:
                _render_copy_preview(
                    str(ch["channel_name"]), draft.get("body", "") or ""
                )

            if ch.get("asset_requirements"):
                with st.expander(f"Asset requirements ({len(ch['asset_requirements'])})"):
                    for a in ch["asset_requirements"]:
                        st.markdown(f"- {a}")

            st.markdown("</div>", unsafe_allow_html=True)

    section_header("Timeline")
    weeks = plan.get("timeline", {}).get("weeks") or []
    if weeks:
        for w in weeks:
            header = f"**Week {w['week_number']}**"
            if w.get("milestones"):
                header += " — " + " · ".join(w["milestones"])
            st.markdown(header)
            acts = w.get("channel_activities") or {}
            for ch_name, items in acts.items():
                if items:
                    st.caption(f"  · {ch_name}: {' / '.join(items)}")
    deps = plan.get("timeline", {}).get("dependencies") or []
    if deps:
        with st.expander("Dependencies"):
            for d in deps:
                st.markdown(f"- {d}")

    with st.expander("QA checkpoints + success metrics"):
        for q in plan.get("qa_checkpoints", []):
            wk = q.get("occurs_at_week")
            st.markdown(
                f"- **{q['name']}**" + (f" (week {wk})" if wk else "") + f" — {q['description']}"
            )
        st.markdown("---")
        for m in plan.get("success_metric_bindings", []):
            st.markdown(
                f"- **{m['metric_name']}** — {m['measurement_approach']}"
                + (f" · owner: {m['owner_placeholder']}" if m.get("owner_placeholder") else "")
            )


    # ---- Section 6 — Review + Approval ---------------------------------

    st.markdown("<a id='review-anchor'></a>", unsafe_allow_html=True)
    section_header("Review and approve")
    st.caption(
        "The AI Critic + four governance scanners audit the plan against the brief. Approve to ship, "
        "regenerate to address findings, or reject to discard."
    )

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        review_clicked = st.button("Run review", type="primary")
    with rc2:
        regen_clicked = st.button(
            "Regenerate plan",
            disabled=st.session_state.review is None,
            help="Re-runs plan generation. Use this to act on Critic findings — the next plan will differ.",
        )
    with rc3:
        approve_clicked = st.button("Approve plan", disabled=st.session_state.review is None)
    with rc4:
        reject_clicked = st.button("Reject plan", disabled=st.session_state.review is None)

    plan_id = plan.get("id")
    if review_clicked and plan_id:
        with st.spinner("Critic + governance + ledger composer running..."):
            code, data = _api_post(f"/api/v1/plans/{plan_id}/review", {}, timeout=180.0)
        if code >= 400:
            styled_error("Could not run the review.", title="Review failed", details=str(data))
        else:
            st.session_state.review = data["validation_report"]
            st.session_state.ledger = data["ledger"]
            st.session_state.plan_status = "in_review" if data.get("blocking") else "draft"
            st.session_state.approve_ack = False
            st.session_state.scroll_target = "review-anchor"
            st.rerun()

    if regen_clicked and st.session_state.brief_id:
        with st.spinner("Generating a new plan..."):
            code, data = _api_post(
                f"/api/v1/briefs/{st.session_state.brief_id}/plan", {}, timeout=180.0
            )
        if code >= 400:
            styled_error("Plan regeneration failed.", title="Regenerate failed", details=str(data))
        else:
            st.session_state.plan = data["plan"]
            st.session_state.copy_drafts = data.get("copy_drafts") or {}
            st.session_state.review = None
            st.session_state.ledger = None
            st.session_state.plan_status = data["plan"].get("status", "draft")
            st.session_state.approve_ack = False
            st.session_state.scroll_target = "plan-anchor"
            callout(
                "Plan regenerated. Run review again to see whether the new draft addresses the prior findings.",
                kind="info",
            )

    if reject_clicked and plan_id:
        code, data = _api_post(f"/api/v1/plans/{plan_id}/reject", {})
        if code >= 400:
            styled_error("Reject failed.", title="Reject failed", details=str(data))
        else:
            st.session_state.plan_status = data["status"]
            callout("Plan rejected. Edit the brief or regenerate to try again.", kind="warning")

    review = st.session_state.review
    blocker_count = error_count = warning_count = info_count = 0
    if review:
        for f in review.get("findings", []):
            sev = f.get("severity")
            if sev == "blocker":
                blocker_count += 1
            elif sev == "error":
                error_count += 1
            elif sev == "warning":
                warning_count += 1
            else:
                info_count += 1

    if approve_clicked and plan_id:
        if (blocker_count + error_count) > 0 and not st.session_state.approve_ack:
            st.session_state.approve_ack = True
            callout(
                f"<strong>{blocker_count} blocker(s) and {error_count} error(s) are still open.</strong> "
                "Tick the acknowledgment below and click <strong>Approve plan</strong> again to ship anyway, "
                "or click <strong>Regenerate plan</strong> to address them first.",
                kind="warning",
            )
        else:
            code, data = _api_post(f"/api/v1/plans/{plan_id}/approve", {})
            if code >= 400:
                styled_error("Approve failed.", title="Approve failed", details=str(data))
            else:
                st.session_state.plan_status = data["status"]
                st.session_state.approve_ack = False
                callout("✅ Plan approved. Use the export buttons below to ship it.", kind="success")

    if st.session_state.approve_ack and (blocker_count + error_count) > 0:
        st.checkbox(
            f"I acknowledge {blocker_count} blocker(s) and {error_count} error(s) and approve anyway.",
            key="approve_ack_checkbox",
        )

    st.caption(f"Status: **{st.session_state.plan_status}**")

    if review:
        align = float(review.get("alignment_score", 0))
        align_color = traffic_color(align)
        st.markdown(
            f"<div class='metric-strip'>"
            f"<div class='metric-cell'><div class='metric-label'>Alignment</div>"
            f"<div class='metric-value' style='color:{align_color}'>{align:.0f}/100</div></div>"
            f"<div class='metric-cell'><div class='metric-label'>Blockers</div>"
            f"<div class='metric-value' style='color:{'var(--danger)' if blocker_count else 'var(--text-primary)'}'>{blocker_count}</div></div>"
            f"<div class='metric-cell'><div class='metric-label'>Errors</div>"
            f"<div class='metric-value' style='color:{'var(--danger)' if error_count else 'var(--text-primary)'}'>{error_count}</div></div>"
            f"<div class='metric-cell'><div class='metric-label'>Warnings</div>"
            f"<div class='metric-value' style='color:{'var(--warning)' if warning_count else 'var(--text-primary)'}'>{warning_count}</div></div>"
            f"<div class='metric-cell'><div class='metric-label'>Info</div>"
            f"<div class='metric-value'>{info_count}</div></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        findings = sorted(
            review.get("findings", []),
            key=lambda f: SEVERITY_RANK.get(f.get("severity", "info"), 99),
        )
        if not findings:
            callout("✅ Critic + governance scanners found no issues.", kind="success")
        # Render each finding as a collapsible <details>. Blockers + errors
        # default open (action required); warnings + info default collapsed
        # so the page isn't dominated by low-priority advisory findings.
        for f in findings:
            sev = f["severity"]
            sev_pill_cls = {"blocker": "blocker", "error": "error", "warning": "warning"}.get(sev, "info")
            card_cls = {
                "blocker": "finding-blocker",
                "error": "finding-error",
                "warning": "finding-warning",
            }.get(sev, "finding-info")
            category = _html.escape(str(f.get("category") or ""))
            description = _html.escape(str(f.get("description") or ""))
            brief_passage = _html.escape(str(f.get("brief_passage") or ""))
            plan_section = _html.escape(str(f.get("plan_section_ref") or ""))
            suggested_fix = _html.escape(str(f.get("suggested_fix") or ""))
            details_html = ""
            if brief_passage:
                details_html += (
                    "<div class='finding-detail'>"
                    "<span class='finding-detail-label'>Brief passage</span>"
                    f"<em>{brief_passage}</em></div>"
                )
            if plan_section:
                details_html += (
                    "<div class='finding-detail'>"
                    "<span class='finding-detail-label'>Plan section</span>"
                    f"<code>{plan_section}</code></div>"
                )
            if suggested_fix:
                details_html += (
                    "<div class='finding-detail'>"
                    "<span class='finding-detail-label'>Suggested fix</span>"
                    f"{suggested_fix}</div>"
                )
            # All findings start collapsed — the metric strip above already shows
            # the headline counts; the reviewer expands a finding only when they
            # want the full detail (brief passage, plan section, suggested fix).
            st.markdown(
                f"<details class='finding-card {card_cls}'>"
                f"<summary>"
                f"{severity_pill(sev_pill_cls, sev.upper())}"
                f"<span class='finding-card-summary-category'>{category}</span>"
                f"<span class='finding-card-summary-desc'>{description}</span>"
                f"</summary>"
                f"<div class='finding-card-body'>"
                f"{details_html}"
                f"</div>"
                f"</details>",
                unsafe_allow_html=True,
            )

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

    plan_id_for_export = plan.get("id") if isinstance(plan, dict) else None
    if plan_id_for_export:
        section_header("Export")
        # Three formats remain: HTML (gantt timeline), PDF (full plan
        # document), PPTX (slide deck for sharing). JSON and Markdown
        # remain on the API surface for tooling but are not exposed here.
        ex_cols = st.columns(3)
        export_specs = [
            ("Download HTML", "gantt", "text/html", "html"),
            ("Download PDF", "pdf", "application/pdf", "pdf"),
            (
                "Download PPTX",
                "pptx",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "presentationml.presentation"
                ),
                "pptx",
            ),
        ]
        for col_idx, (label, fmt, mime, ext) in enumerate(export_specs):
            url = f"{API_BASE}/api/v1/plans/{plan_id_for_export}/export/{fmt}"
            with ex_cols[col_idx]:
                try:
                    with httpx.Client(timeout=30.0) as _c:
                        _r = _c.get(url)
                        if _r.status_code == 200:
                            st.download_button(
                                label,
                                data=_r.content,
                                file_name=f"plan_{plan_id_for_export}.{ext}",
                                mime=mime,
                                # All three buttons share the primary blue
                                # treatment with white text — the global rule
                                # is "blue button → white text" everywhere.
                                type="primary",
                                key=f"export_{fmt}_{plan_id_for_export}",
                                use_container_width=True,
                            )
                        else:
                            st.caption(f"{label}: unavailable ({_r.status_code})")
                except Exception:
                    st.caption(f"{label}: API offline")


if st.session_state.scroll_target:
    scroll_to(st.session_state.scroll_target)
    st.session_state.scroll_target = None
