"""A20 — Canonical Resolver.

Given a list of TerminologyFindings (clusters of variant terms), recommend the canonical
value for each cluster citing the term dictionary entry that authorizes the choice.

Tier 0 priority order:
  1. Deterministic dictionary lookup — if exactly one of the variants is the canonical of
     a term-dictionary entry (or a synonym whose canonical is among the variants), use that
     and cite the dictionary's `rule_ref`. No LLM call needed for the demo path.
  2. LLM fallback — for clusters where the dictionary doesn't disambiguate, call the LLM
     to pick the canonical and produce rationale + a best-guess citation.
"""
from __future__ import annotations

from uuid import UUID

from core.db.repositories import TermDictionaryRepository
from core.db.session import SessionLocal
from core.llm.gateway import call_structured
from core.schemas import (
    CanonicalSuggestion,
    CanonicalSuggestionExtraction,
    TerminologyFinding,
)


def _dictionary_lookup() -> list[dict]:
    """Snapshot of the term dictionary as a list of {term, canonical, synonyms, rule_ref}."""
    try:
        with SessionLocal() as db:
            rows = TermDictionaryRepository(db).list_all()
            return [
                {
                    "term": r.term,
                    "type": r.type,
                    "canonical": r.canonical,
                    "synonyms": list(r.synonyms or []),
                    "rule_ref": r.rule_ref,
                    "notes": r.notes,
                }
                for r in rows
            ]
    except Exception:
        return []


def _resolve_via_dictionary(
    finding: TerminologyFinding, entries: list[dict]
) -> CanonicalSuggestion | None:
    """If exactly one cluster variant maps to a dictionary canonical, recommend it."""
    variants_lc = {v.strip().lower(): v for v in finding.variants}
    if not variants_lc:
        return None

    matches: list[tuple[str, dict]] = []
    for e in entries:
        if e.get("type") != "approved":
            continue
        canonical = (e.get("canonical") or e.get("term") or "").strip()
        if not canonical:
            continue
        canonical_lc = canonical.lower()
        all_forms_lc = {canonical_lc} | {(s or "").strip().lower() for s in e.get("synonyms", [])}
        # Hit if the cluster contains the canonical OR the cluster overlaps the synonyms.
        if variants_lc.keys() & all_forms_lc:
            matches.append((canonical, e))

    if len(matches) != 1:
        return None

    canonical, entry = matches[0]
    rule_ref = entry.get("rule_ref") or "term_dictionary"
    notes = entry.get("notes") or ""
    rationale = (
        f"'{canonical}' is the approved canonical in the term dictionary "
        f"({rule_ref}). Variants {sorted(set(finding.variants) - {canonical})} are listed as "
        f"synonyms or are absent from the approved list."
    )
    if notes:
        rationale += f" {notes}"
    return CanonicalSuggestion(
        cluster_id=finding.cluster_id,
        recommended_value=canonical,
        rationale=rationale,
        citation=rule_ref,
    )


class CanonicalResolver:
    name = "canonical_resolver"

    async def run(
        self,
        findings: list[TerminologyFinding],
        *,
        session_id: UUID | None = None,
    ) -> list[CanonicalSuggestion]:
        if not findings:
            return []

        entries = _dictionary_lookup()
        suggestions: list[CanonicalSuggestion] = []
        unresolved: list[TerminologyFinding] = []

        for f in findings:
            via_dict = _resolve_via_dictionary(f, entries)
            if via_dict is not None:
                suggestions.append(via_dict)
            else:
                unresolved.append(f)

        if unresolved and session_id is not None:
            for f in unresolved:
                try:
                    extraction = await call_structured(
                        prompt_name=self.name,
                        variables={
                            "cluster_id": f.cluster_id,
                            "variants": f.variants,
                            "occurrences": f.occurrences,
                            "term_dictionary": entries,
                        },
                        output_schema=CanonicalSuggestionExtraction,
                        session_id=session_id,
                        agent_name=self.name,
                    )
                except Exception:
                    continue
                suggestions.append(
                    CanonicalSuggestion(
                        cluster_id=extraction.cluster_id or f.cluster_id,
                        recommended_value=extraction.recommended_value,
                        rationale=extraction.rationale,
                        citation=extraction.citation or "llm_inference",
                    )
                )

        return suggestions
