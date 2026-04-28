"""Exemplar retrieval — embeds a brief, finds top-k similar exemplar briefs in Qdrant.

Tier 0 fallback: if Qdrant is empty (no exemplars indexed yet) or embeddings are unavailable,
returns an empty list. The Planner will still work — it just won't have few-shot grounding.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from core.config import get_settings
from core.embeddings.client import embed_one, is_embeddings_available
from core.embeddings.qdrant_store import QdrantStore, SearchHit
from core.schemas import Brief

EXEMPLARS_DIR = Path(__file__).resolve().parents[1] / "seeds" / "exemplar_briefs"
COLLECTION = "briefs_v1"


@dataclass(frozen=True, slots=True)
class Exemplar:
    name: str  # filename stem
    body: str
    score: float


async def index_exemplar_briefs(store: QdrantStore | None = None) -> int:
    """Embed every `seeds/exemplar_briefs/*.md` and upsert into Qdrant. Idempotent (overwrites by id-of-name)."""
    if not is_embeddings_available():
        return 0
    store = store or QdrantStore()
    items: list[tuple[str, list[float], dict]] = []
    for md in sorted(EXEMPLARS_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        vec = await embed_one(text)
        items.append((_stable_id(md.stem), vec, {"name": md.stem, "body": text}))
    store.upsert_many(COLLECTION, items)
    return len(items)


async def retrieve_exemplars(brief: Brief, *, top_k: int = 3) -> list[Exemplar]:
    if not is_embeddings_available():
        return []
    store = QdrantStore()
    if not store.collection_exists(COLLECTION):
        return []
    query_text = _brief_query_text(brief)
    try:
        vec = await embed_one(query_text)
    except Exception:
        return []
    hits: list[SearchHit] = store.search(COLLECTION, vec, top_k=top_k)
    return [
        Exemplar(name=h.payload.get("name", "unknown"), body=h.payload.get("body", ""), score=h.score)
        for h in hits
    ]


def _brief_query_text(brief: Brief) -> str:
    parts = [
        f"Campaign: {brief.campaign_name}",
        f"Objective: {brief.business_objective}",
        f"Audience: {brief.target_audience.raw_description}",
        f"Key message: {brief.key_message}",
    ]
    if brief.channels:
        parts.append("Channels: " + ", ".join(c.name for c in brief.channels))
    return "\n".join(parts)


def _stable_id(name: str) -> str:
    """Deterministic UUID from a name so re-indexing overwrites instead of duplicating."""
    import hashlib

    h = hashlib.sha1(name.encode("utf-8")).hexdigest()
    # Format as UUID
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
