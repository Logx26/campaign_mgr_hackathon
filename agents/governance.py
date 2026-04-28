"""Deterministic governance scanners run alongside the LLM Critic.

These are rule-based checks that catch concrete violations the Critic might miss or
hand-wave: prohibited terms in copy, CTAs not in approved formats, copy exceeding length,
mandatory inclusions absent. Cheap, deterministic, citable.
"""
from __future__ import annotations

import re

from agents.copy_drafter import load_copy_drafts
from core.db.repositories import TermDictionaryRepository
from core.db.session import SessionLocal
from core.schemas import ValidationFinding
from core.state import CampaignState
from knowledge.channel_spec_library import get_channel_spec


def _term_lookup() -> tuple[dict[str, str | None], set[str]]:
    """Returns (prohibited_term_lc → canonical_or_none, approved_term_lc_set)."""
    with SessionLocal() as db:
        repo = TermDictionaryRepository(db)
        prohibited = {r.term.lower(): r.canonical for r in repo.list_by_type("prohibited")}
        approved = {r.term.lower() for r in repo.list_by_type("approved")}
    return prohibited, approved


def scan_prohibited_terms_in_copy(state: CampaignState) -> list[ValidationFinding]:
    if state.plan is None:
        return []
    drafts = load_copy_drafts(state.session_id, state.plan.id)
    if not drafts:
        return []

    prohibited, _approved = _term_lookup()
    findings: list[ValidationFinding] = []

    for ch in state.plan.channels:
        d = drafts.get(str(ch.id))
        if not d:
            continue
        body = (d.get("body") or "").lower()
        for term, canonical in prohibited.items():
            # Whole-word match.
            if re.search(rf"\b{re.escape(term)}\b", body):
                fix = (
                    f"Replace '{term}' in {ch.channel_name} copy with '{canonical}'."
                    if canonical
                    else f"Remove '{term}' from {ch.channel_name} copy and rewrite the surrounding sentence with a concrete claim."
                )
                findings.append(
                    ValidationFinding(
                        category="compliance",
                        severity="error",
                        brief_passage="Brand voice guidelines (term dictionary)",
                        plan_section_ref=f"channels[{ch.channel_name}].copy_draft.body",
                        description=f"{ch.channel_name} copy contains prohibited term '{term}'.",
                        suggested_fix=fix,
                    )
                )
    return findings


def scan_cta_against_spec(state: CampaignState) -> list[ValidationFinding]:
    if state.plan is None:
        return []
    findings: list[ValidationFinding] = []
    for ch in state.plan.channels:
        spec = get_channel_spec(ch.channel_name)
        if not spec:
            continue
        approved = [c.lower() for c in (spec.get("approved_cta_formats") or [])]
        prohibited = [c.lower() for c in (spec.get("prohibited_cta_formats") or [])]
        cta_lc = (ch.cta or "").strip().lower()
        if not cta_lc:
            continue
        if cta_lc in prohibited:
            findings.append(
                ValidationFinding(
                    category="compliance",
                    severity="blocker",
                    brief_passage=f"{ch.channel_name} channel spec — prohibited_cta_formats",
                    plan_section_ref=f"channels[{ch.channel_name}].cta",
                    description=f"{ch.channel_name} CTA '{ch.cta}' is in the channel's prohibited list.",
                    suggested_fix=(
                        f"Replace with one of the approved CTAs: {', '.join(spec.get('approved_cta_formats') or []) or '(none configured)'}."
                    ),
                )
            )
            continue
        if approved and cta_lc not in approved:
            findings.append(
                ValidationFinding(
                    category="consistency",
                    severity="warning",
                    brief_passage=f"{ch.channel_name} channel spec — approved_cta_formats",
                    plan_section_ref=f"channels[{ch.channel_name}].cta",
                    description=f"{ch.channel_name} CTA '{ch.cta}' is not in the channel's approved list.",
                    suggested_fix=(
                        f"Use one of: {', '.join(spec.get('approved_cta_formats') or []) or '(none configured)'}."
                    ),
                )
            )
    return findings


def scan_copy_length(state: CampaignState) -> list[ValidationFinding]:
    if state.plan is None:
        return []
    drafts = load_copy_drafts(state.session_id, state.plan.id)
    if not drafts:
        return []
    findings: list[ValidationFinding] = []
    for ch in state.plan.channels:
        spec = get_channel_spec(ch.channel_name)
        max_words = spec.get("max_length_words") if spec else None
        if not max_words:
            continue
        d = drafts.get(str(ch.id))
        if not d:
            continue
        body = d.get("body") or ""
        word_count = len(body.split())
        if word_count > int(max_words) * 1.15:  # 15% tolerance
            findings.append(
                ValidationFinding(
                    category="feasibility",
                    severity="warning",
                    brief_passage=f"{ch.channel_name} channel spec — max_length_words={max_words}",
                    plan_section_ref=f"channels[{ch.channel_name}].copy_draft.body",
                    description=f"{ch.channel_name} copy is {word_count} words; spec max is {max_words}.",
                    suggested_fix=f"Tighten {ch.channel_name} copy to ≤ {max_words} words.",
                )
            )
    return findings


def scan_mandatory_inclusions(state: CampaignState) -> list[ValidationFinding]:
    """If brief.constraints.mandatory_inclusions are present, every copy draft body should reference them."""
    if state.brief is None or state.plan is None:
        return []
    inclusions = list(state.brief.constraints.mandatory_inclusions or [])
    if not inclusions:
        return []
    drafts = load_copy_drafts(state.session_id, state.plan.id)
    if not drafts:
        return []

    findings: list[ValidationFinding] = []
    # We don't require EVERY channel to mention EVERY inclusion — only flag if NOT A SINGLE channel
    # references a given mandatory inclusion (then it's clearly missing from the plan entirely).
    aggregate = " ".join(((drafts.get(str(ch.id)) or {}).get("body") or "") for ch in state.plan.channels).lower()
    for inc in inclusions:
        keyword = re.sub(r"[^a-z0-9 ]", "", inc.lower()).split()[:3]
        if not keyword:
            continue
        if not any(k in aggregate for k in keyword):
            findings.append(
                ValidationFinding(
                    category="compliance",
                    severity="error",
                    brief_passage=f"constraints.mandatory_inclusions: '{inc}'",
                    plan_section_ref="channels[*].copy_draft.body",
                    description=f"Mandatory inclusion '{inc}' is not referenced in any channel's copy.",
                    suggested_fix=f"Ensure at least one channel references '{inc}' in copy or asset notes.",
                )
            )
    return findings


def run_all_scanners(state: CampaignState) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    findings.extend(scan_cta_against_spec(state))
    findings.extend(scan_prohibited_terms_in_copy(state))
    findings.extend(scan_copy_length(state))
    findings.extend(scan_mandatory_inclusions(state))
    return findings
