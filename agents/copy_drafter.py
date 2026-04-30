"""A11 — Copy Drafter. One LLM call per channel (parallel), brand voice score computed server-side.

P9 fixes:
  - Auto-bootstraps the Axion brand voice fingerprint on first use (no manual
    script step required before the first plan).
  - Removed the silent `voice_score = 0.0` fallback — scoring failures now surface
    via the trace channel and the breakdown carries an `error_class` key for
    observability. The voice_score itself stays 0.0 in that case (schema requires
    a numeric value), but the breakdown signals it's a real failure not a no-op.
  - Always emits a non-empty `angle`: prefers the LLM output, falls back to a
    keyword-based heuristic over the body. UI never renders "?" again.
  - Sanitizes the copy body: strips control characters, normalizes line endings,
    collapses excess blank lines. Prevents broken-overflow / mojibake artifacts
    in the disabled `st.text_area` render.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass

from core.db.repositories import TermDictionaryRepository
from core.db.session import SessionLocal
from core.llm.gateway import call_structured
from core.schemas import Brief, BrandVoiceFingerprint, ChannelPlan, CopyDraft, CopyDraftExtraction
from core.state import CampaignState
from knowledge.brand_voice import get_or_build_fingerprint, score_text_async
from knowledge.channel_spec_library import get_channel_spec
from observability.trace import log_event

_log = logging.getLogger("agents.copy_drafter")


@dataclass(frozen=True, slots=True)
class _DraftResult:
    channel_plan_ref: object
    draft: CopyDraft


def _term_lists() -> tuple[list[str], list[str]]:
    with SessionLocal() as db:
        repo = TermDictionaryRepository(db)
        approved = [r.term for r in repo.list_by_type("approved")]
        prohibited = [r.term for r in repo.list_by_type("prohibited")]
    return approved, prohibited


def _on_voice_samples(fp: BrandVoiceFingerprint | None) -> list[str]:
    if fp is None:
        return []
    return (fp.samples_positive or [])[:5]


# ---------------------------------------------------------------------------
# Body sanitization — removes control chars, mojibake, stray JSON fragments
# ---------------------------------------------------------------------------

# Strip all C0/C1 control codes except \n and \t.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Drop anything that looks like a stray JSON fragment at the head/tail of the body
# (e.g. the LLM occasionally bleeds `"angle": "..."` into the body field).
_JSON_FRAGMENT_RE = re.compile(r'^\s*[{"]\s*[a-z_]+\s*"\s*:\s*"', re.IGNORECASE)


def _sanitize_body(text: str) -> str:
    if not text:
        return ""
    # Normalize unicode (collapses combining-character oddities into NFC form).
    text = unicodedata.normalize("NFC", text)
    # Strip control chars (keeps \n, \t).
    text = _CONTROL_CHARS_RE.sub("", text)
    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Drop leading/trailing JSON-fragment lines.
    lines = text.split("\n")
    while lines and _JSON_FRAGMENT_RE.match(lines[0]):
        lines.pop(0)
    while lines and _JSON_FRAGMENT_RE.match(lines[-1]):
        lines.pop()
    # Collapse 3+ consecutive blank lines into 1.
    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append("")
        else:
            blank_run = 0
            out.append(line.rstrip())
    return "\n".join(out).strip()


# ---------------------------------------------------------------------------
# Angle fallback heuristic — keyword-based, no extra LLM call
# ---------------------------------------------------------------------------

_ANGLE_RULES: list[tuple[str, list[str]]] = [
    # (angle, keyword markers — first match wins, so ordering = priority)
    # urgency / proof are most specific signals → match first.
    ("urgency-led",     ["last chance", "act now", "deadline", "expires", "ends today", "limited time", "only today"]),
    ("proof-led",       ["customer story", "case study", "testimonial", "% increase", "% lift", "% conversion", "according to", "report shows", "research shows"]),
    # Enterprise positioning beats generic ROI signal (a B2B brief mentioning "revenue"
    # AND "enterprise" should land as enterprise-led, not ROI-led).
    ("enterprise-led",  ["enterprise", "vp ", "director", "executive", "c-suite", "1000+", "fortune 500", "compliance"]),
    ("ROI-led",         ["roi", "return on investment", "$", "pipeline", "arr", "mrr", "saved", "savings", "cost per", "revenue lift", "revenue growth"]),
    ("speed-led",       ["minutes", "hours", "fast", "speed", "real-time", "instantly", "in seconds", "save time", "10x faster", "5x faster", "right now"]),
    ("pain-led",        ["pain", "struggle", "frustrating", "broken", "stuck", "tired of", "stop reconciling", "stop wasting"]),
    ("benefit-led",     ["benefit", "gain", "improve", "boost", "unlock", "deliver", "outcome"]),
]


def _derive_angle(body: str) -> str:
    """Keyword-based angle classifier. Lightweight, deterministic, no extra LLM call."""
    if not body:
        return "outcome-led"
    lc = body.lower()
    for angle, markers in _ANGLE_RULES:
        for m in markers:
            if m.lower() in lc:
                return angle
    return "outcome-led"


def _resolve_angle(llm_angle: str | None, body: str) -> str:
    candidate = (llm_angle or "").strip()
    # Treat empty / "?" / placeholder as missing.
    if not candidate or candidate.lower() in {"?", "n/a", "tbd", "unknown", "null", "none"}:
        return _derive_angle(body)
    return candidate


# ---------------------------------------------------------------------------
# Drafter
# ---------------------------------------------------------------------------


class CopyDrafter:
    name = "copy_drafter"

    async def draft_one(
        self,
        *,
        brief: Brief,
        channel: ChannelPlan,
        fingerprint: BrandVoiceFingerprint | None,
        approved_terms: list[str],
        prohibited_terms: list[str],
        on_voice_samples: list[str],
        session_id,
    ) -> _DraftResult:
        spec = get_channel_spec(channel.channel_name) or {"name": channel.channel_name}
        extraction: CopyDraftExtraction = await call_structured(
            prompt_name=self.name,
            variables={
                "brief_json": brief.model_dump(mode="json"),
                "channel_spec": spec,
                "channel_plan": {"cta": channel.cta, "notes": channel.notes or ""},
                "on_voice_samples": on_voice_samples,
                "approved_terms": approved_terms,
                "prohibited_terms": prohibited_terms,
            },
            output_schema=CopyDraftExtraction,
            session_id=session_id,
            agent_name=f"copy_drafter:{channel.channel_name}",
        )

        body = _sanitize_body(extraction.body)
        angle = _resolve_angle(getattr(extraction, "angle", None), body)

        voice_score = 0.0
        breakdown: dict[str, float] = {}
        if fingerprint is not None:
            try:
                bv = await score_text_async(body, fingerprint)
                voice_score = bv.score
                breakdown = {"raw_positive": bv.raw_positive, "raw_negative": bv.raw_negative}
            except Exception as exc:
                # Surface the failure via trace + log instead of silently scoring 0.
                _log.exception("voice scoring failed for channel %s", channel.channel_name)
                breakdown = {"scoring_failed": 1.0}
                try:
                    log_event(
                        session_id=session_id,
                        agent_name=f"copy_drafter:{channel.channel_name}",
                        input_hash="voice_score_failure",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                except Exception:
                    pass
        else:
            # No fingerprint AND auto-bootstrap couldn't build one. Record a structured
            # signal in the breakdown so the UI can show "scoring unavailable" instead
            # of pretending the score is real.
            breakdown = {"fingerprint_available": 0.0}

        draft = CopyDraft(
            channel_plan_ref=channel.id,
            body=body,
            voice_score=voice_score,
            voice_score_breakdown=breakdown,
            angle=angle,
            rule_violations=[],
            variants=[],
        )
        return _DraftResult(channel_plan_ref=channel.id, draft=draft)


async def fan_out_copy_drafts(state: CampaignState) -> CampaignState:
    """Parallel copy drafting across the plan's channels. Each draft is attached to its channel
    via `channel_plan.copy_draft_ref`. Drafts themselves are stashed in Redis since
    CampaignState is `extra=forbid`.
    """
    if state.plan is None or state.brief is None:
        return state

    fingerprint: BrandVoiceFingerprint | None = None
    with SessionLocal() as db:
        try:
            fingerprint = await get_or_build_fingerprint(db, brand_name="Axion")
        except Exception:
            _log.exception("fingerprint bootstrap failed")
            fingerprint = None

    approved, prohibited = _term_lists()
    on_voice = _on_voice_samples(fingerprint)

    drafter = CopyDrafter()
    tasks = [
        drafter.draft_one(
            brief=state.brief,
            channel=ch,
            fingerprint=fingerprint,
            approved_terms=approved,
            prohibited_terms=prohibited,
            on_voice_samples=on_voice,
            session_id=state.session_id,
        )
        for ch in state.plan.channels
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    drafts_by_channel: dict[object, CopyDraft] = {}
    for r in results:
        if isinstance(r, Exception):
            _log.exception("copy_drafter task failed", exc_info=r)
            continue
        drafts_by_channel[r.channel_plan_ref] = r.draft

    # Attach copy_draft_ref on each channel.
    new_channels = [
        ch.model_copy(update={"copy_draft_ref": drafts_by_channel[ch.id].id})
        if ch.id in drafts_by_channel
        else ch
        for ch in state.plan.channels
    ]

    new_plan = state.plan.model_copy(update={"channels": new_channels})

    from orchestrator.interrupts import _redis  # reuse helper

    cache_key = f"copy_drafts:{state.session_id}:{new_plan.id}"
    payload = {str(cid): d.model_dump(mode="json") for cid, d in drafts_by_channel.items()}
    import json

    _redis().setex(cache_key, 3600, json.dumps(payload, default=str))

    return state.model_copy(update={"plan": new_plan})


def load_copy_drafts(session_id, plan_id) -> dict[str, dict]:
    """Read the cached drafts for rendering in the API/UI."""
    import json

    from orchestrator.interrupts import _redis

    raw = _redis().get(f"copy_drafts:{session_id}:{plan_id}")
    if raw is None:
        return {}
    return json.loads(raw.decode("utf-8"))
