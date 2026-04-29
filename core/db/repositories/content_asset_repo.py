"""Content asset persistence (W3)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from core.db import models


class ContentAssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        body: str,
        source_name: str | None = None,
        channel: str | None = None,
        audience_hint: str | None = None,
        embedding_ref: str | None = None,
    ) -> models.ContentAsset:
        row = models.ContentAsset(
            body=body,
            source_name=source_name,
            channel=channel,
            audience_hint=audience_hint,
            embedding_ref=embedding_ref,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, asset_id: UUID) -> models.ContentAsset | None:
        return (
            self.db.query(models.ContentAsset)
            .filter(models.ContentAsset.id == asset_id)
            .first()
        )

    def get_many(self, asset_ids: list[UUID]) -> list[models.ContentAsset]:
        if not asset_ids:
            return []
        return list(
            self.db.query(models.ContentAsset)
            .filter(models.ContentAsset.id.in_(asset_ids))
            .all()
        )


class ConsistencyReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        asset_ids: list[UUID],
        report_json: dict,
    ) -> models.ConsistencyReport:
        row = models.ConsistencyReport(
            asset_ids=[str(a) for a in asset_ids],
            report_json=report_json,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, report_id: UUID) -> models.ConsistencyReport | None:
        return (
            self.db.query(models.ConsistencyReport)
            .filter(models.ConsistencyReport.id == report_id)
            .first()
        )
