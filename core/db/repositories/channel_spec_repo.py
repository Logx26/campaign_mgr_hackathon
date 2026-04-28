"""Channel spec library access."""
from sqlalchemy.orm import Session

from core.db import models


class ChannelSpecRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: str) -> models.ChannelSpec | None:
        return self.db.query(models.ChannelSpec).filter(models.ChannelSpec.name == name).first()

    def list_all(self) -> list[models.ChannelSpec]:
        return list(self.db.query(models.ChannelSpec).order_by(models.ChannelSpec.name.asc()))

    def upsert_by_name(self, name: str, spec_json: dict, version: int = 1) -> models.ChannelSpec:
        existing = self.get_by_name(name)
        if existing is not None:
            existing.spec_json = spec_json
            existing.version = version
            self.db.flush()
            return existing
        row = models.ChannelSpec(name=name, version=version, spec_json=spec_json)
        self.db.add(row)
        self.db.flush()
        return row
