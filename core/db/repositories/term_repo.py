"""Term dictionary access."""
from sqlalchemy.orm import Session

from core.db import models


class TermDictionaryRepository:
    def __init__(self, db: Session):
        self.db = db

    def find(self, term: str) -> models.TermDictionaryEntry | None:
        return (
            self.db.query(models.TermDictionaryEntry)
            .filter(models.TermDictionaryEntry.term.ilike(term))
            .first()
        )

    def list_by_type(self, type_: str) -> list[models.TermDictionaryEntry]:
        return list(
            self.db.query(models.TermDictionaryEntry)
            .filter(models.TermDictionaryEntry.type == type_)
            .order_by(models.TermDictionaryEntry.term.asc())
        )

    def list_all(self) -> list[models.TermDictionaryEntry]:
        return list(
            self.db.query(models.TermDictionaryEntry).order_by(
                models.TermDictionaryEntry.term.asc()
            )
        )

    def upsert(
        self,
        term: str,
        type_: str,
        synonyms: list[str] | None = None,
        canonical: str | None = None,
        rule_ref: str | None = None,
        notes: str | None = None,
    ) -> models.TermDictionaryEntry:
        existing = self.find(term)
        if existing is not None:
            existing.type = type_
            existing.synonyms = synonyms or []
            existing.canonical = canonical
            existing.rule_ref = rule_ref
            existing.notes = notes
            self.db.flush()
            return existing
        row = models.TermDictionaryEntry(
            term=term,
            type=type_,
            synonyms=synonyms or [],
            canonical=canonical,
            rule_ref=rule_ref,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        return row
