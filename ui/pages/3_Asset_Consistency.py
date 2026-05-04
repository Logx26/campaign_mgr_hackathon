"""Asset Consistency — multi-asset terminology + CTA scan.

Build asset cards one at a time (start with three; click "+ Add asset" for more).
The system clusters terminology variants, scans CTAs against the rule catalog, and
recommends canonicals from the brand dictionary.
"""
from __future__ import annotations

import html as _html
import json
import os
from pathlib import Path

import httpx
import streamlit as st
import yaml as _yaml

from ui.styles import (
    PRODUCT_NAME,
    callout,
    inject_global_css,
    render_banner,
    section_header,
    severity_pill,
    styled_error,
    top_header,
    traffic_color,
)


st.set_page_config(
    page_title=f"{PRODUCT_NAME} · Asset Consistency",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
top_header()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def _api_post(path: str, payload: dict | None = None, timeout: float = 120.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


# ---------------------------------------------------------------------------
# Session state — list of asset slots. Each slot has a stable key so widgets keep
# their values across reruns even when other slots are removed.
# ---------------------------------------------------------------------------

if "asset_slots" not in st.session_state:
    # Stable string keys so removing slot 2 doesn't shift slot 3's widget identity.
    st.session_state.asset_slots = ["a1", "a2", "a3"]
    st.session_state.asset_next_id = 4
if "w3_report" not in st.session_state:
    st.session_state.w3_report = None


def _add_slot():
    slot_id = f"a{st.session_state.asset_next_id}"
    st.session_state.asset_next_id += 1
    st.session_state.asset_slots.append(slot_id)


def _remove_slot(slot_id: str):
    if len(st.session_state.asset_slots) > 1:
        st.session_state.asset_slots = [s for s in st.session_state.asset_slots if s != slot_id]


# ---------------------------------------------------------------------------
# Demo D — pre-fill the 5 sample assets from `seeds/sample_assets/*.yaml`.
#
# Triggered by the Get Started page setting `_launch_demo == "D"` then
# switching to this page. We must populate session_state for each slot's
# widget keys BEFORE the widgets render below, otherwise the widgets'
# `value=` arg loses to Streamlit's preserved widget state.
# ---------------------------------------------------------------------------


def _load_demo_assets() -> None:
    """Pre-fill the asset slots from `_demo_d_assets` populated by the Get
    Started page on click. Falls back to reading YAMLs from disk only if
    that key is missing — the Get Started flow always pre-loads first."""
    assets: list[dict] = list(st.session_state.get("_demo_d_assets") or [])
    if not assets:
        # Defensive fallback — Get Started should always pre-load this list,
        # but if a future caller sets `_launch_demo == "D"` without populating
        # the list (e.g. tests or a raw URL), read the YAMLs directly.
        seeds_root = Path(__file__).resolve().parents[2] / "seeds" / "sample_assets"
        for path in sorted(seeds_root.glob("asset_*.yaml")) if seeds_root.exists() else []:
            try:
                data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            assets.append(
                {
                    "source": str(data.get("source_name") or ""),
                    "channel": str(data.get("channel") or ""),
                    "audience": str(data.get("audience_hint") or ""),
                    "body": str(data.get("body") or "").strip(),
                }
            )
    if not assets:
        return
    # Reserve fresh slot ids so any prior add/remove activity doesn't collide.
    base = max(
        (int(s.lstrip("a") or 0) for s in st.session_state.asset_slots),
        default=0,
    ) + 1
    new_slots: list[str] = []
    for i, asset in enumerate(assets):
        slot_id = f"a{base + i}"
        new_slots.append(slot_id)
        st.session_state[f"source_{slot_id}"] = str(asset.get("source") or "")
        st.session_state[f"channel_{slot_id}"] = str(asset.get("channel") or "")
        st.session_state[f"audience_{slot_id}"] = str(asset.get("audience") or "")
        st.session_state[f"body_{slot_id}"] = str(asset.get("body") or "")
    st.session_state.asset_slots = new_slots
    st.session_state.asset_next_id = base + len(assets)


if st.session_state.get("_launch_demo") == "D":
    _load_demo_assets()
    st.session_state["_launch_demo"] = None
    st.session_state.pop("_demo_d_assets", None)


render_banner(
    "Asset Consistency",
    "Add your marketing assets below. The system clusters terminology variants, flags CTA "
    "drift, and recommends canonicals from the brand dictionary.",
)


# ---------------------------------------------------------------------------
# Asset card builder
# ---------------------------------------------------------------------------

section_header("Assets")

for idx, slot_id in enumerate(st.session_state.asset_slots, start=1):
    # The slot label is now a small inline pill at the top-left of the card,
    # not a full-width header band — it reads as a tag, not a section heading,
    # and visually separates from the white input fields below.
    st.markdown(
        f"<div class='asset-card-frame'>"
        f"<span class='asset-card-pill'>Asset {idx}</span>",
        unsafe_allow_html=True,
    )
    cols = st.columns([3, 3, 2, 1])
    with cols[0]:
        st.text_input("Source name", key=f"source_{slot_id}", placeholder="e.g. LinkedIn post · Q3 launch")
    with cols[1]:
        st.text_input("Channel", key=f"channel_{slot_id}", placeholder="e.g. LinkedIn, Email, SDR")
    with cols[2]:
        st.text_input("Audience hint", key=f"audience_{slot_id}", placeholder="e.g. RevOps, SMB")
    with cols[3]:
        if st.button("Remove", key=f"remove_{slot_id}", use_container_width=True):
            _remove_slot(slot_id)
            st.rerun()
    st.text_area(
        "Asset body",
        key=f"body_{slot_id}",
        height=140,
        placeholder="Paste the asset copy or marketing body here…",
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)


bc1, bc2, _spacer = st.columns([1, 1, 4])
with bc1:
    if st.button("➕ Add asset", use_container_width=True):
        _add_slot()
        st.rerun()


# Collect parsed assets from the slots that have a body.
parsed_assets: list[dict] = []
for slot_id in st.session_state.asset_slots:
    body = (st.session_state.get(f"body_{slot_id}") or "").strip()
    if not body:
        continue
    parsed_assets.append(
        {
            "body": body,
            "source_name": (st.session_state.get(f"source_{slot_id}") or "").strip() or None,
            "channel": (st.session_state.get(f"channel_{slot_id}") or "").strip() or None,
            "audience_hint": (st.session_state.get(f"audience_{slot_id}") or "").strip() or None,
        }
    )

st.caption(f"{len(parsed_assets)} asset(s) ready.")

run_clicked = st.button(
    "Run consistency scan",
    type="primary",
    disabled=len(parsed_assets) < 1,
)

if run_clicked:
    with st.spinner("Scanning…"):
        code, data = _api_post("/api/v1/consistency/scan", {"assets": parsed_assets})
    if code >= 400:
        styled_error("The scan could not complete.", title="Scan failed", details=str(data))
    else:
        st.session_state.w3_report = data["report"]


# ---------------------------------------------------------------------------
# Render the report — visual cards instead of report-style headings
# ---------------------------------------------------------------------------

if st.session_state.w3_report:
    report = st.session_state.w3_report
    idx = float(report.get("overall_consistency_index", 1.0))
    color = traffic_color(idx * 100)

    section_header("Consistency report")

    n_term = len(report.get("terminology_findings") or [])
    cta_findings = report.get("cta_findings") or []
    n_inconsistent_cta = sum(1 for c in cta_findings if not c.get("is_consistent"))

    # Headline tile with the consistency index.
    st.markdown(
        f"<div class='score-tile'>"
        f"<div class='score-tile-label'>Overall consistency</div>"
        f"<div class='score-tile-value' style='color:{color}'>"
        f"{idx:.2f}<span class='score-tile-denom'> / 1.00</span></div>"
        f"<div class='score-tile-sub'>"
        f"<span class='pill pill-warning' style='margin-right:6px'>{n_term} terminology drift</span>"
        f"<span class='pill pill-warning'>{n_inconsistent_cta} of {len(cta_findings)} CTA drift</span>"
        f"</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Terminology cluster cards.
    term_findings = sorted(
        report.get("terminology_findings") or [],
        key=lambda t: (-len(t.get("variants", [])), -sum((t.get("occurrences") or {}).values())),
    )

    if term_findings:
        st.markdown("<h3 style='margin-top:14px'>Terminology clusters</h3>", unsafe_allow_html=True)
        for t in term_findings:
            variants = t.get("variants") or []
            canonical = t.get("canonical")
            occurrences = t.get("occurrences") or {}
            chips = "".join(
                f"<span class='pill pill-warning' style='margin-right:6px; margin-bottom:4px'>"
                f"{_html.escape(str(v))} × {occurrences.get(v, 0)}</span>"
                for v in variants
            )
            canon_html = ""
            if canonical:
                canon_html = (
                    f"<div style='margin-top:8px; color:var(--text-secondary); font-size:0.88rem'>"
                    f"Recommended canonical: <strong style='color:var(--accent)'>"
                    f"{_html.escape(canonical)}</strong>"
                    f"</div>"
                )
            st.markdown(
                f"<div class='lumeo-card'>"
                f"<div style='margin-bottom:6px'>{chips}</div>"
                f"<div style='color:var(--text-muted); font-size:0.78rem; text-transform:uppercase; "
                f"letter-spacing:0.06em; font-weight:600'>"
                f"Affects {len(t.get('affected_asset_ids') or [])} asset(s)</div>"
                f"{canon_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Canonical recommendations with citation.
    suggestions = report.get("canonical_suggestions") or []
    if suggestions:
        st.markdown("<h3 style='margin-top:14px'>Canonical recommendations</h3>", unsafe_allow_html=True)
        for s in suggestions:
            citation = _html.escape(str(s.get("citation") or "?"))
            recommended = _html.escape(str(s.get("recommended_value") or ""))
            rationale = _html.escape(str(s.get("rationale") or ""))
            st.markdown(
                f"<div class='lumeo-card'>"
                f"<div style='display:flex; align-items:baseline; gap:10px; flex-wrap:wrap'>"
                f"<strong style='color:var(--accent); font-size:1.05rem'>→ {recommended}</strong>"
                f"<span class='lumeo-caption'>cite: {citation}</span>"
                f"</div>"
                f"<div style='color:var(--text-secondary); font-size:0.9rem; margin-top:6px; line-height:1.55'>"
                f"{rationale}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # CTA findings — grouped by canonical / drift / unconfigured.
    if cta_findings:
        st.markdown("<h3 style='margin-top:14px'>Calls to action</h3>", unsafe_allow_html=True)
        for c in cta_findings:
            raw = _html.escape(str(c.get("raw_cta") or ""))
            canonical = c.get("canonical_cta")
            consistent = c.get("is_consistent")
            asset_id_short = (c.get('asset_id', '') or '')[:8]
            if consistent:
                st.markdown(
                    f"<div class='lumeo-card' style='border-left:4px solid var(--success); padding:10px 14px'>"
                    f"{severity_pill('success', 'CANONICAL')} "
                    f"<strong>{raw}</strong> "
                    f"<span class='lumeo-caption'>· asset {asset_id_short}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            elif canonical:
                cn = _html.escape(str(canonical))
                st.markdown(
                    f"<div class='lumeo-card' style='border-left:4px solid var(--warning); padding:10px 14px'>"
                    f"{severity_pill('warning', 'NORMALIZE')} "
                    f"<span style='text-decoration:line-through; color:var(--text-muted)'>{raw}</span> "
                    f"→ <strong style='color:var(--accent)'>{cn}</strong> "
                    f"<span class='lumeo-caption'>· asset {asset_id_short}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='lumeo-card' style='border-left:4px solid var(--info); padding:10px 14px'>"
                    f"{severity_pill('info', 'UNCONFIGURED')} "
                    f"<strong>{raw}</strong> "
                    f"<span class='lumeo-caption'>· no canonical configured · asset {asset_id_short}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    if not term_findings and not cta_findings:
        callout("✅ All assets are consistent. No terminology drift or CTA mismatches detected.", kind="success")

    st.download_button(
        "Download report JSON",
        data=json.dumps(report, indent=2, default=str),
        file_name=f"consistency_report_{report.get('id', 'consistency')}.json",
        mime="application/json",
    )
