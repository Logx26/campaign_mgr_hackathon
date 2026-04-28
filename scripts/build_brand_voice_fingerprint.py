"""One-shot CLI: read seeds/brand_voice_samples and persist a BrandVoiceFingerprint row.

Usage:
    python scripts/build_brand_voice_fingerprint.py            # default brand "Axion"
    python scripts/build_brand_voice_fingerprint.py --brand X  # custom brand
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.session import SessionLocal  # noqa: E402
from knowledge.brand_voice import build_fingerprint, load_lines, persist_fingerprint  # noqa: E402

SAMPLES_DIR = PROJECT_ROOT / "seeds" / "brand_voice_samples"


async def _main(brand: str, on_voice: Path, off_voice: Path) -> None:
    pos = load_lines(on_voice)
    neg = load_lines(off_voice)
    print(f"Building fingerprint for '{brand}' from {len(pos)} on-voice + {len(neg)} off-voice lines...")
    fp = await build_fingerprint(brand, pos, neg)
    with SessionLocal() as db:
        persist_fingerprint(db, fp)
        db.commit()
    print(f"  persisted: id={fp.id}  dim={fp.embedding_dim}  model={fp.embedding_model}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", default="Axion")
    parser.add_argument("--on-voice", type=Path, default=SAMPLES_DIR / "axion_on_voice.txt")
    parser.add_argument("--off-voice", type=Path, default=SAMPLES_DIR / "axion_off_voice.txt")
    args = parser.parse_args()
    asyncio.run(_main(args.brand, args.on_voice, args.off_voice))


if __name__ == "__main__":
    main()
