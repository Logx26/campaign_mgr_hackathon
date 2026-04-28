"""A11 — Copy Drafter. One LLM call per channel (parallel), brand voice score computed server-side."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.db.repositories import TermDictionaryRepository
from core.db.session import SessionLocal
from core.llm.gateway import call_structured
from core.schemas import Brief, BrandVoiceFingerprint, ChannelPlan, CopyDraft, CopyDraftExtraction
from core.state import CampaignState
from knowledge.brand_voice import load_fingerprint, score_text_async
from knowledge.channel_spec_library import get_channel_spec


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

        # Compute voice score if a fingerprint is available; otherwise default to 0.
        voice_score = 0.0
        breakdown: dict[str, float] = {}
        if fingerprint is not None:
            try:
                bv = await score_text_async(extraction.body, fingerprint)
                voice_score = bv.score
                breakdown = {"raw_positive": bv.raw_positive, "raw_negative": bv.raw_negative}
            except Exception:
                voice_score = 0.0

        draft = CopyDraft(
            channel_plan_ref=channel.id,
            body=extraction.body,
            voice_score=voice_score,
            voice_score_breakdown=breakdown,
            rule_violations=[],  # rule scanner is Tier 1
            variants=[],
        )
        return _DraftResult(channel_plan_ref=channel.id, draft=draft)


async def fan_out_copy_drafts(state: CampaignState) -> CampaignState:
    """Parallel copy drafting across the plan's channels. Each draft is attached to its channel
    via `channel_plan.copy_draft_ref`. The drafts themselves are stashed on the plan object via
    a transient attribute pattern: we serialize them into the plan_json blob from the API layer.
    """
    if state.plan is None or state.brief is None:
        return state

    fingerprint = None
    with SessionLocal() as db:
        fingerprint = load_fingerprint(db, brand_name="Axion")

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

    # Stash drafts under a side dict via the state's `error` slot? No — better to extend
    # CampaignState. We keep CampaignState strict, so the API layer reads drafts from a
    # session-scoped Redis cache.
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
