"""Kill-switch fallback page — renders a static narrated demo from cached JSON when the
live API or DB has died mid-presentation. No API calls. No external state.

The user lands here when they click "Fallback view" on the launcher, OR when a live demo
catches an unrecoverable error and routes here as a graceful exit.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from ui.styles import inject_global_css, render_banner, severity_pill, styled_error

st.set_page_config(page_title="Axion · Fallback", layout="wide")
inject_global_css()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FALLBACK_DIR = _PROJECT_ROOT / "seeds" / "demo_fallback"

letter = st.session_state.get("_launch_demo", "A").upper()
fallback_path = _FALLBACK_DIR / f"demo_{letter.lower()}.json"

if not fallback_path.is_file():
    render_banner("Fallback unavailable", "No cached payload for this demo.", tags=["fallback"])
    styled_error(f"Expected fallback payload at <code>{fallback_path}</code>.", title="Missing fallback")
    st.stop()

payload = json.loads(fallback_path.read_text(encoding="utf-8"))

render_banner(
    f"Demo {letter} · {payload.get('title', '')}",
    payload.get("narration", ""),
    tags=["fallback", f"demo {letter}"],
)

st.info(
    "You're on the kill-switch fallback view — this renders entirely from a pre-recorded payload. "
    "Use this when the live API is down or a flow gets stuck mid-presentation."
)

# ---------- per-demo render -----------------------------------------------

if letter == "A":
    c1, c2, c3 = st.columns(3)
    c1.metric("Alignment", f"{payload['alignment_score']}/100")
    c2.metric("Completeness", f"{payload['completeness_score']}/100")
    c3.metric("Channels", ", ".join(payload["channels_chosen"]))
    st.markdown("**Sample finding**")
    st.markdown(f"<div class='axion-card'>{payload['sample_finding']}</div>", unsafe_allow_html=True)
    st.markdown("**Assumption ledger excerpt**")
    for e in payload.get("ledger_excerpt", []):
        st.markdown(
            f"- <code>{e['field']}</code> · basis <strong>{e['basis']}</strong> · cite: <em>{e['citation']}</em>",
            unsafe_allow_html=True,
        )

elif letter == "B":
    c1, c2 = st.columns(2)
    c1.metric("Completeness before", f"{payload['completeness_before']}/100")
    c2.metric("Completeness after", f"{payload['completeness_after']}/100",
              delta=int(payload["completeness_after"]) - int(payload["completeness_before"]))
    st.markdown(f"**{payload['questions_emitted']} clarifying questions emitted**")
    for q in payload.get("sample_questions", []):
        st.markdown(
            f"<div class='axion-card'>"
            f"<strong>{q['prompt']}</strong><br>"
            f"<span class='pill pill-info'>{q['type']}</span> · "
            f"<code>{q['field']}</code> · suggested: <em>{q['default']}</em>"
            f"</div>",
            unsafe_allow_html=True,
        )

elif letter == "C":
    sev_pill = severity_pill("blocker", "BLOCKER") if payload.get("blocking") else severity_pill("success", "CLEAN")
    st.markdown(
        f"**Alignment: {payload['alignment_score']}/100** · {sev_pill}",
        unsafe_allow_html=True,
    )
    st.markdown("### Top findings")
    for f in payload.get("top_findings", []):
        st.markdown(
            f"<div class='axion-card'>"
            f"{severity_pill(f['severity'], f['severity'].upper())} "
            f"<strong>{f['category']}</strong> — {f['description']}<br>"
            f"<span style='color:var(--text-2)'>Fix:</span> {f['fix']}"
            f"</div>",
            unsafe_allow_html=True,
        )

elif letter == "D":
    st.metric("Overall consistency", f"{payload['consistency_index']:.2f}")
    st.markdown("### Terminology clusters")
    for cluster in payload.get("terminology_clusters", []):
        variants = ", ".join(cluster["variants"])
        occurrences = ", ".join(f"<code>{k}</code> × {v}" for k, v in cluster["occurrences"].items())
        st.markdown(
            f"<div class='axion-card'>"
            f"🔁 <strong>{variants}</strong><br>"
            f"<span style='color:var(--text-2)'>Occurrences:</span> {occurrences}<br>"
            f"<span style='color:var(--text-2)'>Canonical:</span> <strong>{cluster['canonical']}</strong> "
            f"<em>(cite: {cluster['citation']})</em>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("### CTA findings")
    for c in payload.get("cta_findings", []):
        if c["consistent"]:
            st.markdown(f"✅ <strong>{c['raw']}</strong>", unsafe_allow_html=True)
        else:
            st.markdown(
                f"🎯 <span style='text-decoration:line-through;color:var(--text-2)'>{c['raw']}</span> → "
                f"<strong>{c['canonical']}</strong>",
                unsafe_allow_html=True,
            )

else:
    styled_error(f"Unknown demo letter: {letter}", title="Demo not found")
