"""Qdrant store wrapper — upsert, search, delete on the Tier 0 collections.

Collections (`briefs_v1`, `plans_v1`, `assets_v1`, `terms_v1`) are bootstrapped by
`scripts/seed_db.py`. This module assumes they exist; it does not create them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.config import get_settings


COLLECTIONS = ("briefs_v1", "plans_v1", "assets_v1", "terms_v1")


@dataclass(frozen=True, slots=True)
class SearchHit:
    point_id: str
    score: float
    payload: dict[str, Any]


class QdrantStore:
    def __init__(self, client: QdrantClient | None = None):
        self._client = client or QdrantClient(url=get_settings().QDRANT_URL)

    @property
    def client(self) -> QdrantClient:
        return self._client

    # ------------------------------------------------------------------ ops

    def upsert(
        self,
        collection: str,
        point_id: str | UUID,
        vector: list[float],
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._client.upsert(
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=str(point_id),
                    vector=vector,
                    payload=payload or {},
                )
            ],
        )

    def upsert_many(
        self,
        collection: str,
        items: list[tuple[str | UUID, list[float], dict[str, Any] | None]],
    ) -> None:
        if not items:
            return
        points = [
            qmodels.PointStruct(id=str(pid), vector=vec, payload=pl or {})
            for pid, vec, pl in items
        ]
        self._client.upsert(collection_name=collection, points=points)

    def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter_: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        """Vector search.

        qdrant-client >= 1.10 removed `client.search` in favor of `query_points`.
        We prefer the new API, with a graceful fallback for older installs.
        """
        qfilter = qmodels.Filter(**filter_) if filter_ else None
        if hasattr(self._client, "query_points"):
            response = self._client.query_points(
                collection_name=collection,
                query=vector,
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
            )
            scored = response.points
        else:  # pragma: no cover — legacy path
            scored = self._client.search(
                collection_name=collection,
                query_vector=vector,
                limit=top_k,
                query_filter=qfilter,
            )
        return [
            SearchHit(point_id=str(h.id), score=float(h.score), payload=h.payload or {})
            for h in scored
        ]

    def delete(self, collection: str, point_ids: list[str | UUID]) -> None:
        if not point_ids:
            return
        self._client.delete(
            collection_name=collection,
            points_selector=qmodels.PointIdsList(points=[str(p) for p in point_ids]),
        )

    def collection_exists(self, name: str) -> bool:
        try:
            existing = {c.name for c in self._client.get_collections().collections}
            return name in existing
        except Exception:
            return False
