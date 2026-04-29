"""A17 — CTA Scanner.

Walks each asset, detects CTA candidates via regex from `rules/cta_patterns.yaml`,
returns one CTAFinding per asset reporting the matched canonical (or `is_consistent=False`
when an asset's CTA is prohibited / unrecognised).

Regex first; LLM fallback runs only when no regex matches an asset (the asset may carry
a CTA we don't have a pattern for, like SDR-style "open to a 15-minute call?").
"""
from __future__ import annotations

import re
from uuid import UUID, uuid4

from core.llm.gateway import call_structured
from core.rules.loader import load_cta_patterns
from core.schemas import CTAFinding, CTAFindingExtraction


# Compiled patterns are cached per-process so we don't recompile on every scan.
_compiled: list[tuple[dict, list[re.Pattern]]] | None = None


def _ensure_compiled() -> list[tuple[dict, list[re.Pattern]]]:
    global _compiled
    if _compiled is not None:
        return _compiled
    rules = load_cta_patterns() or []
    out: list[tuple[dict, list[re.Pattern]]] = []
    for rule in rules:
        pats = []
        for p in rule.get("patterns", []):
            try:
                pats.append(re.compile(p))
            except re.error:
                continue
        out.append((rule, pats))
    _compiled = out
    return out


def reset_pattern_cache() -> None:
    """Test hook — clear compiled pattern cache between rule edits."""
    global _compiled
    _compiled = None


def _match_first(body: str) -> tuple[dict, str] | None:
    """Walk rules in YAML order (prohibited first), return first (rule, matched_text)."""
    for rule, pats in _ensure_compiled():
        for pat in pats:
            m = pat.search(body)
            if m:
                return rule, m.group(0)
    return None


class CTAScanner:
    name = "cta_scanner"

    async def run(
        self,
        assets: list[dict],
        *,
        session_id: UUID | None = None,
    ) -> list[CTAFinding]:
        findings: list[CTAFinding] = []
        for a in assets:
            asset_id = a.get("id")
            if isinstance(asset_id, str):
                asset_id = UUID(asset_id)
            elif asset_id is None:
                asset_id = uuid4()
            body = a.get("body") or ""

            match = _match_first(body)
            if match is not None:
                rule, raw = match
                status = rule.get("status")
                canonical = rule.get("canonical")
                rule_id = rule.get("id")
                # Approved canonicals are consistent iff the raw verbatim ALREADY equals the canonical
                # (case-insensitive). If it's a synonym (e.g. "schedule a call" → "Book a demo"),
                # mark inconsistent so the report flags the drift.
                is_consistent = (
                    status == "approved"
                    and canonical is not None
                    and raw.strip().lower() == canonical.strip().lower()
                )
                findings.append(
                    CTAFinding(
                        asset_id=asset_id,
                        raw_cta=raw,
                        normalized_cta=canonical,
                        canonical_cta=canonical,
                        is_consistent=is_consistent,
                        rule_id=rule_id,
                    )
                )
                continue

            # No regex matched — try the LLM fallback if a session is supplied.
            llm_finding = await self._llm_fallback(asset_id, body, session_id=session_id)
            if llm_finding is not None:
                findings.append(llm_finding)

        return findings

    async def _llm_fallback(
        self,
        asset_id: UUID,
        body: str,
        *,
        session_id: UUID | None,
    ) -> CTAFinding | None:
        if session_id is None or not body.strip():
            return None
        try:
            extraction = await call_structured(
                prompt_name=self.name,
                variables={"body": body},
                output_schema=CTAFindingExtraction,
                session_id=session_id,
                agent_name=self.name,
            )
        except Exception:
            return None

        if not extraction.is_cta or not extraction.raw_cta.strip():
            return None
        return CTAFinding(
            asset_id=asset_id,
            raw_cta=extraction.raw_cta,
            normalized_cta=extraction.normalized_cta,
            canonical_cta=None,  # outside our pattern catalog — resolver may suggest one
            is_consistent=False,
            rule_id=None,
        )
