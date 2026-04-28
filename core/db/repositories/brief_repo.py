"""Brief CRUD + override append. Briefs are never mutated; overrides are appended."""
from uuid import UUID

from sqlalchemy.orm import Session

from core.db import models
from core.schemas import Brief as BriefSchema


class BriefRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, brief: BriefSchema, session_id: UUID | None = None) -> models.Brief:
        row = models.Brief(
            id=brief.id,
            session_id=session_id,
            raw_source=brief.raw_source,
            source_format=brief.source_format,
            parsed_json=brief.model_dump(mode="json"),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, brief_id: UUID) -> models.Brief | None:
        return self.db.get(models.Brief, brief_id)

    def add_override(
        self,
        brief_id: UUID,
        field_path: str,
        new_value: str,
        old_value: str | None = None,
        reason: str | None = None,
    ) -> models.BriefOverride:
        ov = models.BriefOverride(
            brief_id=brief_id,
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        self.db.add(ov)
        self.db.flush()
        return ov

    def list_overrides(self, brief_id: UUID) -> list[models.BriefOverride]:
        return list(
            self.db.query(models.BriefOverride)
            .filter(models.BriefOverride.brief_id == brief_id)
            .order_by(models.BriefOverride.created_at.asc())
        )
