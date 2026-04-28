"""Seed Postgres + bootstrap Qdrant collections.

Idempotent: safe to re-run. Loads:
  - channel specs from seeds/channel_specs.yaml
  - term dictionary from seeds/term_dictionary.yaml
  - plan templates from seeds/plan_templates.yaml (Tier 1 sketches)
  - exemplar briefs from seeds/exemplar_briefs/*.md (text only — embeddings happen P5)
And ensures Qdrant has the 4 Tier 0 collections.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import yaml
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_settings  # noqa: E402
from core.db import models  # noqa: E402
from core.db.repositories import ChannelSpecRepository, TermDictionaryRepository  # noqa: E402
from core.db.session import SessionLocal  # noqa: E402

SEEDS = PROJECT_ROOT / "seeds"

def _qdrant_collections() -> list[tuple[str, int]]:
    """Use the configured EMBEDDING_DIM so collections match the deployed model."""
    dim = get_settings().EMBEDDING_DIM
    return [
        ("briefs_v1", dim),
        ("plans_v1", dim),
        ("assets_v1", dim),
        ("terms_v1", dim),
    ]


def seed_channel_specs(db) -> int:
    repo = ChannelSpecRepository(db)
    data = yaml.safe_load((SEEDS / "channel_specs.yaml").read_text(encoding="utf-8"))
    count = 0
    for spec in data.get("channels", []):
        json_payload = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in spec.items()}
        repo.upsert_by_name(name=spec["name"], spec_json=json_payload, version=spec.get("version", 1))
        count += 1
    return count


def seed_term_dictionary(db) -> int:
    repo = TermDictionaryRepository(db)
    data = yaml.safe_load((SEEDS / "term_dictionary.yaml").read_text(encoding="utf-8"))
    count = 0
    for entry in data.get("terms", []):
        repo.upsert(
            term=entry["term"],
            type_=entry["type"],
            synonyms=entry.get("synonyms") or [],
            canonical=entry.get("canonical"),
            rule_ref=entry.get("rule_ref"),
            notes=entry.get("notes"),
        )
        count += 1
    return count


def seed_plan_templates(db) -> int:
    data = yaml.safe_load((SEEDS / "plan_templates.yaml").read_text(encoding="utf-8"))
    count = 0
    for tpl in data.get("templates", []):
        existing = (
            db.query(models.PlanTemplate).filter(models.PlanTemplate.name == tpl["name"]).first()
        )
        if existing is not None:
            existing.template_json = tpl
        else:
            db.add(models.PlanTemplate(name=tpl["name"], template_json=tpl))
        count += 1
    db.flush()
    return count


def count_exemplar_briefs() -> int:
    """Texts are loaded into Qdrant at P5. P1 just confirms they exist on disk."""
    exemplar_dir = SEEDS / "exemplar_briefs"
    return len(list(exemplar_dir.glob("*.md")))


def bootstrap_qdrant(*, force_recreate: bool = False) -> int:
    """Ensure the 4 Tier 0 collections exist at the configured EMBEDDING_DIM.

    If `force_recreate=True`, existing collections are deleted and rebuilt at the new dim
    (use this after switching embedding models — Qdrant fixes dim at create time).
    """
    settings = get_settings()
    client = QdrantClient(url=settings.QDRANT_URL)
    existing = {c.name for c in client.get_collections().collections}
    created = 0
    for name, dim in _qdrant_collections():
        if name in existing:
            if not force_recreate:
                continue
            client.delete_collection(name)
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
        )
        created += 1
    return created


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed Postgres + bootstrap Qdrant.")
    parser.add_argument(
        "--recreate-qdrant",
        action="store_true",
        help="Drop and recreate Qdrant collections at the current EMBEDDING_DIM. "
        "Use after switching embedding models (e.g. -large 3072 → -small 1536).",
    )
    args = parser.parse_args()

    print("== Seeding Postgres ==")
    with SessionLocal() as db:
        n_specs = seed_channel_specs(db)
        n_terms = seed_term_dictionary(db)
        n_templates = seed_plan_templates(db)
        db.commit()
    n_exemplars = count_exemplar_briefs()

    print(f"  channel_specs:    {n_specs}")
    print(f"  term_dictionary:  {n_terms}")
    print(f"  plan_templates:   {n_templates}")
    print(f"  exemplar_briefs:  {n_exemplars} on disk (loaded into Qdrant in P5)")

    print(f"== Bootstrapping Qdrant (dim={get_settings().EMBEDDING_DIM}) ==")
    n_collections = bootstrap_qdrant(force_recreate=args.recreate_qdrant)
    if args.recreate_qdrant:
        print(f"  recreated {n_collections} collection(s) at dim={get_settings().EMBEDDING_DIM}")
    else:
        print(f"  created {n_collections} new collection(s); existing collections preserved")

    print("Done.")


if __name__ == "__main__":
    main()
