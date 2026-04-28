"""Thin async wrapper exposed as a tool primitive (will be wrapped in MCP at Tier 1)."""
from __future__ import annotations

from knowledge.brand_voice import BrandVoiceScore, score_text_async
from core.schemas import BrandVoiceFingerprint


async def score(text: str, fingerprint: BrandVoiceFingerprint) -> BrandVoiceScore:
    return await score_text_async(text, fingerprint)
