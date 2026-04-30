"""Brand voice fingerprinting + scoring.

A fingerprint is the centroid of embeddings over an "on-voice" sample set, plus the
centroid of an "off-voice" set. Scoring any text is then:
    score = cos_sim(text, positive) - 0.5 * cos_sim(text, negative)
mapped to 0–100. Cheap, deterministic, no fine-tuning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session as DbSession

from core.config import get_settings
from core.db import models
from core.embeddings.client import embed_many, embed_one, is_embeddings_available
from core.schemas import BrandVoiceFingerprint


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        raise ValueError("cannot compute centroid of empty vector set")
    arr = np.array(vectors, dtype=float)
    centroid = arr.mean(axis=0)
    return centroid.tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    av = np.array(a, dtype=float)
    bv = np.array(b, dtype=float)
    na = float(np.linalg.norm(av))
    nb = float(np.linalg.norm(bv))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(av, bv) / (na * nb))


@dataclass(slots=True)
class BrandVoiceScore:
    score: float  # 0-100
    raw_positive: float  # cosine to positive centroid (-1..1)
    raw_negative: float  # cosine to negative centroid (-1..1)


def score_text(text: str, fingerprint: BrandVoiceFingerprint, vector: list[float] | None = None) -> BrandVoiceScore:
    """Score `text` against `fingerprint`. Pass `vector` to skip a re-embed if already available."""
    if vector is None:
        # Synchronous wrapper — used from non-async contexts. Caller must ensure embeddings live.
        import asyncio

        vector = asyncio.run(embed_one(text))
    pos = _cosine(vector, fingerprint.positive_centroid)
    neg = _cosine(vector, fingerprint.negative_centroid)
    raw = pos - 0.5 * neg  # roughly in [-1.5, 1.5]
    # Map [-1.5, 1.5] → [0, 100]
    pct = max(0.0, min(100.0, (raw + 1.5) / 3.0 * 100.0))
    return BrandVoiceScore(score=round(pct, 1), raw_positive=pos, raw_negative=neg)


async def score_text_async(
    text: str, fingerprint: BrandVoiceFingerprint
) -> BrandVoiceScore:
    """Async variant — embeds + scores in the running event loop."""
    vector = await embed_one(text)
    return score_text(text, fingerprint, vector=vector)


async def build_fingerprint(
    brand_name: str,
    positive_samples: list[str],
    negative_samples: list[str],
) -> BrandVoiceFingerprint:
    if not is_embeddings_available():
        raise RuntimeError("Embeddings deployment unavailable — cannot build fingerprint")
    if len(positive_samples) < 5:
        raise ValueError("Need at least 5 on-voice samples for a stable fingerprint")
    if len(negative_samples) < 3:
        raise ValueError("Need at least 3 off-voice samples for a stable fingerprint")

    pos_vectors = await embed_many(positive_samples)
    neg_vectors = await embed_many(negative_samples)

    settings = get_settings()
    return BrandVoiceFingerprint(
        brand_name=brand_name,
        positive_centroid=_centroid(pos_vectors),
        negative_centroid=_centroid(neg_vectors),
        samples_positive=positive_samples,
        samples_negative=negative_samples,
        embedding_model=settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT,
        embedding_dim=settings.EMBEDDING_DIM,
    )


def persist_fingerprint(db: DbSession, fp: BrandVoiceFingerprint) -> models.BrandVoiceFingerprint:
    row = models.BrandVoiceFingerprint(
        id=fp.id,
        brand_name=fp.brand_name,
        positive_centroid=fp.positive_centroid,
        negative_centroid=fp.negative_centroid,
        samples_positive=fp.samples_positive,
        samples_negative=fp.samples_negative,
        embedding_model=fp.embedding_model,
        embedding_dim=fp.embedding_dim,
        built_at=fp.built_at,
    )
    db.add(row)
    db.flush()
    return row


def load_fingerprint(db: DbSession, brand_name: str) -> BrandVoiceFingerprint | None:
    row = (
        db.query(models.BrandVoiceFingerprint)
        .filter(models.BrandVoiceFingerprint.brand_name == brand_name)
        .order_by(models.BrandVoiceFingerprint.built_at.desc())
        .first()
    )
    if row is None:
        return None
    return BrandVoiceFingerprint(
        id=row.id,
        brand_name=row.brand_name,
        positive_centroid=row.positive_centroid,
        negative_centroid=row.negative_centroid,
        samples_positive=row.samples_positive or [],
        samples_negative=row.samples_negative or [],
        embedding_model=row.embedding_model,
        embedding_dim=row.embedding_dim,
        built_at=row.built_at,
    )


def load_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def get_or_build_fingerprint(
    db: DbSession,
    brand_name: str,
    *,
    seeds_dir: Path | None = None,
) -> BrandVoiceFingerprint | None:
    """Load the fingerprint for `brand_name`; build + persist it on first use.

    Used by the Copy Drafter so the demo doesn't require a manual
    `python scripts/build_brand_voice_fingerprint.py` step before the first plan.

    Returns None if the fingerprint doesn't exist AND embeddings are unavailable
    (cannot bootstrap), AND the seeds directory is missing — caller decides what
    to do (the Copy Drafter currently surfaces a non-zero scoring-failed sentinel).
    """
    existing = load_fingerprint(db, brand_name=brand_name)
    if existing is not None:
        return existing

    if not is_embeddings_available():
        return None

    if seeds_dir is None:
        seeds_dir = Path(__file__).resolve().parents[1] / "seeds" / "brand_voice_samples"
    on_voice_path = seeds_dir / f"{brand_name.lower()}_on_voice.txt"
    off_voice_path = seeds_dir / f"{brand_name.lower()}_off_voice.txt"
    if not on_voice_path.is_file() or not off_voice_path.is_file():
        return None

    pos = load_lines(on_voice_path)
    neg = load_lines(off_voice_path)
    if len(pos) < 5 or len(neg) < 3:
        return None

    fp = await build_fingerprint(brand_name, pos, neg)
    persist_fingerprint(db, fp)
    db.commit()
    return fp
