"""W3 — Multi-asset consistency scan.

Paste 3–30 asset bodies (separated by `---`), or click "Load demo assets" to pre-fill
with the 5-asset Axion drift set. The scan groups variant terminology, scans CTAs against
the rule catalog, and recommends canonicals citing the term dictionary.

Bonus button — "Scan this plan's copy drafts" — pulls a recent ExecutionPlan's per-channel
copy draft bodies as the asset set, demonstrating that W3 audits W1's own outputs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import streamlit as st
import yaml

from ui.styles import inject_global_css, render_banner, styled_error


st.set_page_config(page_title="Axion · Multi-asset Consistency", layout="wide")
inject_global_css()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_ASSETS_DIR = _PROJECT_ROOT / "seeds" / "sample_assets"


def _api_post(path: str, payload: dict | None = None, timeout: float = 120.0) -> tuple[int, dict]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API_BASE}{path}", json=payload or {})
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data


def _index_color(idx: float) -> str:
    if idx >= 0.85:
        return "green"
    if idx >= 0.6:
        return "orange"
    return "red"


def _load_demo_assets() -> str:
    if not _SAMPLE_ASSETS_DIR.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(_SAMPLE_ASSETS_DIR.glob("asset_*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        header_bits = []
        if data.get("source_name"):
            header_bits.append(f"# {data['source_name']}")
        if data.get("channel"):
            header_bits.append(f"# Channel: {data['channel']}")
        if data.get("audience_hint"):
            header_bits.append(f"# Audience: {data['audience_hint']}")
        body = data.get("body") or ""
        chunks.append("\n".join([*header_bits, "", body.strip()]))
    return "\n\n---\n\n".join(chunks)


def _parse_assets(text: str) -> list[dict]:
    """Parse the textarea into [{body, source_name, channel, audience_hint}]."""
    if not text.strip():
        return []
    blocks = [b.strip() for b in text.split("\n---\n") if b.strip()]
    if len(blocks) <= 1:
        # Allow `---` not surrounded by blank lines.
        blocks = [b.strip() for b in text.split("---") if b.strip()]
    out: list[dict] = []
    for b in blocks:
        source_name = None
        channel = None
        audience_hint = None
        body_lines: list[str] = []
        for line in b.splitlines():
            if line.startswith("# Channel:"):
                channel = line.replace("# Channel:", "").strip() or None
            elif line.startswith("# Audience:"):
                audience_hint = line.replace("# Audience:", "").strip() or None
            elif line.startswith("# ") and source_name is None:
                source_name = line[2:].strip() or None
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if body:
            out.append(
                {
                    "body": body,
                    "source_name": source_name,
                    "channel": channel,
                    "audience_hint": audience_hint,
                }
            )
    return out


# -------- Session state ---------------------------------------------------

for key, default in [
    ("w3_assets_text", ""),
    ("w3_report", None),
    ("w3_asset_ids", []),
    ("w3_plan_id_input", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


render_banner(
    "W3 · Multi-asset Consistency",
    "Paste 3–30 marketing assets separated by `---`. The scanner clusters terminology variants, "
    "checks CTAs against the rule catalog, and recommends canonicals citing the term dictionary.",
    tags=["W3", "consistency"],
)

# Auto-load demo D if user came from launcher.
if st.session_state.get("_launch_demo") == "D" and not st.session_state.get("w3_assets_text"):
    st.session_state["w3_assets_text"] = _load_demo_assets()
    st.session_state["_launch_demo"] = None


col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("Load demo assets (Axion drift set)"):
        st.session_state.w3_assets_text = _load_demo_assets()
        st.session_state.w3_report = None
with col_b:
    plan_id = st.text_input(
        "Plan ID (optional — for 'Scan this plan's copy drafts')",
        value=st.session_state.w3_plan_id_input,
        key="w3_plan_id_input",
        help="Pull copy draft bodies from a generated plan as the asset set.",
    )
    scan_plan_clicked = st.button(
        "Scan this plan's copy drafts",
        disabled=not plan_id.strip(),
        help="Cross-system flex: W3 audits W1's own outputs.",
    )


assets_text = st.text_area(
    "Asset bodies (use `---` between assets)",
    height=380,
    key="w3_assets_text",
)
parsed = _parse_assets(st.session_state.w3_assets_text)
st.caption(f"{len(parsed)} asset(s) parsed.")

run_clicked = st.button("Run consistency scan", type="primary", disabled=len(parsed) < 1)

if run_clicked:
    with st.spinner("Scanning…"):
        code, data = _api_post("/api/v1/consistency/scan", {"assets": parsed})
    if code >= 400:
        styled_error(f"({code}) <code>{data}</code>", title="Scan failed")
    else:
        st.session_state.w3_report = data["report"]
        st.session_state.w3_asset_ids = data.get("asset_ids", [])

if scan_plan_clicked:
    with st.spinner("Pulling plan copy drafts…"):
        code, data = _api_post(f"/api/v1/consistency/scan_from_plan/{plan_id.strip()}", {})
    if code >= 400:
        styled_error(f"({code}) <code>{data}</code>", title="Scan failed")
    else:
        st.session_state.w3_report = data["report"]
        st.session_state.w3_asset_ids = data.get("asset_ids", [])
        st.success(f"Scanned {len(data.get('asset_ids', []))} channel copy drafts from plan {plan_id.strip()}")


# -------- Render the report ----------------------------------------------

if st.session_state.w3_report:
    report = st.session_state.w3_report
    idx = float(report.get("overall_consistency_index", 1.0))
    color = _index_color(idx)

    st.markdown("---")
    headline_col, count_col = st.columns([2, 1])
    with headline_col:
        st.markdown(
            f"**Overall consistency:** "
            f"<span style='color:{color}; font-size:2rem; font-weight:600'>{idx:.2f}</span> "
            f"<span style='color:#888'>(1.0 = perfect alignment)</span>",
            unsafe_allow_html=True,
        )
    with count_col:
        n_term = len(report.get("terminology_findings") or [])
        cta_findings = report.get("cta_findings") or []
        n_inconsistent_cta = sum(1 for c in cta_findings if not c.get("is_consistent"))
        st.markdown(
            f"**Drift signals:** "
            f"🔁 {n_term} terminology · "
            f"🎯 {n_inconsistent_cta}/{len(cta_findings)} CTA"
        )

    # Top Issues — biggest clusters first, then inconsistent CTAs.
    term_findings = sorted(
        report.get("terminology_findings") or [],
        key=lambda t: (-len(t.get("variants", [])), -sum((t.get("occurrences") or {}).values())),
    )
    if term_findings or n_inconsistent_cta:
        st.markdown("### Top Issues")
        shown = 0
        for t in term_findings:
            if shown >= 3:
                break
            variants = t.get("variants") or []
            canonical = t.get("canonical")
            if len(variants) < 2:
                continue
            recommendation = f" → canonical: **{canonical}**" if canonical else ""
            st.markdown(f"🔁 **Terminology drift** — {', '.join(variants)}{recommendation}")
            shown += 1
        for c in cta_findings:
            if shown >= 3:
                break
            if c.get("is_consistent"):
                continue
            raw = c.get("raw_cta", "")
            cn = c.get("canonical_cta") or "(no canonical configured)"
            st.markdown(f"🎯 **CTA drift** — ~~{raw}~~ → **{cn}**")
            shown += 1

    # Terminology findings
    st.markdown("### Terminology clusters")
    for t in term_findings or []:
        variants = t.get("variants") or []
        occurrences = t.get("occurrences") or {}
        canonical = t.get("canonical")
        title = (
            f"🔁 {t.get('cluster_id')} — {len(variants)} variants"
            f" — canonical: **{canonical}**" if canonical else f"🔁 {t.get('cluster_id')} — {len(variants)} variants"
        )
        with st.expander(title):
            st.markdown("**Variants:** " + ", ".join(variants))
            st.markdown(
                "**Occurrences:** "
                + ", ".join(f"`{k}` × {v}" for k, v in occurrences.items())
            )
            if canonical:
                st.markdown(f"**Recommended canonical:** {canonical}")
            st.caption(f"Affects {len(t.get('affected_asset_ids') or [])} asset(s).")

    # Canonical suggestions (rationale + citation)
    suggestions = report.get("canonical_suggestions") or []
    if suggestions:
        st.markdown("### Canonical recommendations")
        for s in suggestions:
            with st.expander(f"{s['cluster_id']} → **{s['recommended_value']}** _(cite: {s.get('citation', '?')})_"):
                st.markdown(s.get("rationale") or "_no rationale_")

    # CTA findings (per asset)
    if cta_findings:
        st.markdown("### CTA findings")
        for c in cta_findings:
            raw = c.get("raw_cta", "")
            canonical = c.get("canonical_cta")
            consistent = c.get("is_consistent")
            if consistent:
                st.markdown(f"✅ {c.get('asset_id', '')[:8]}… — **{raw}** _(canonical match)_")
            elif canonical:
                st.markdown(f"🎯 {c.get('asset_id', '')[:8]}… — ~~{raw}~~ → **{canonical}** _(rule: {c.get('rule_id') or 'n/a'})_")
            else:
                st.markdown(f"⚠️ {c.get('asset_id', '')[:8]}… — **{raw}** _(no canonical configured)_")

    st.download_button(
        "Download report JSON",
        data=json.dumps(report, indent=2, default=str),
        file_name=f"consistency_report_{report.get('id', 'w3')}.json",
        mime="application/json",
    )
