"""Consistency report composer — deterministic aggregation + index math."""
from __future__ import annotations

from uuid import uuid4

from agents.consistency_report_composer import compose_report
from core.schemas import CanonicalSuggestion, CTAFinding, TerminologyFinding


def test_perfect_alignment_index_is_one():
    aid = uuid4()
    cta = [
        CTAFinding(
            asset_id=aid,
            raw_cta="Book a demo",
            canonical_cta="Book a demo",
            is_consistent=True,
            rule_id="cta_book_a_demo",
        )
    ]
    report = compose_report(asset_ids=[aid], terminology=[], cta=cta, suggestions=[])
    assert report.overall_consistency_index == 1.0
    assert len(report.cta_findings) == 1
    assert report.terminology_findings == []


def test_canonical_promoted_into_terminology_finding():
    cluster = TerminologyFinding(
        cluster_id="cluster_0",
        variants=["AI-powered", "AI-assisted"],
        occurrences={"AI-powered": 3, "AI-assisted": 2},
        affected_asset_ids=[uuid4(), uuid4()],
    )
    suggestion = CanonicalSuggestion(
        cluster_id="cluster_0",
        recommended_value="AI-assisted",
        rationale="Term dictionary canonical.",
        citation="brand_book_§3.1",
    )
    report = compose_report(
        asset_ids=[uuid4()],
        terminology=[cluster],
        cta=[],
        suggestions=[suggestion],
    )
    assert report.terminology_findings[0].canonical == "AI-assisted"


def test_index_drops_with_drift():
    """Two-variant cluster across 5 mentions + one inconsistent CTA out of 3 = drift signal 2 / 8 → 0.75."""
    aid_set = [uuid4() for _ in range(5)]
    term = TerminologyFinding(
        cluster_id="c0",
        variants=["AI-powered", "AI-assisted"],
        occurrences={"AI-powered": 3, "AI-assisted": 2},
        affected_asset_ids=aid_set,
    )
    cta = [
        CTAFinding(asset_id=aid_set[0], raw_cta="Book a demo", canonical_cta="Book a demo", is_consistent=True),
        CTAFinding(asset_id=aid_set[1], raw_cta="Book a demo", canonical_cta="Book a demo", is_consistent=True),
        CTAFinding(
            asset_id=aid_set[2],
            raw_cta="Schedule a call",
            canonical_cta="Book a demo",
            is_consistent=False,
        ),
    ]
    report = compose_report(asset_ids=aid_set, terminology=[term], cta=cta, suggestions=[])
    # drift_signal = (2 - 1) + 1 = 2; total_signal = 5 + 3 = 8; index = 1 - 2/8 = 0.75
    assert report.overall_consistency_index == 0.75
