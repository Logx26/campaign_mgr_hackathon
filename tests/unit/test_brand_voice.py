"""Brand voice scoring math — pure cosine, no embeddings call."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from core.schemas import BrandVoiceFingerprint
from knowledge.brand_voice import _centroid, _cosine, score_text


def test_centroid_of_unit_vectors():
    c = _centroid([[1.0, 0.0], [0.0, 1.0]])
    assert c == [0.5, 0.5]


def test_cosine_identity_one():
    assert _cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0


def test_cosine_orthogonal_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_score_text_high_when_aligned_with_positive_centroid():
    fp = BrandVoiceFingerprint(
        id=uuid4(),
        brand_name="X",
        positive_centroid=[1.0, 0.0, 0.0],
        negative_centroid=[0.0, 1.0, 0.0],
        embedding_model="mock",
        embedding_dim=3,
        built_at=datetime.utcnow(),
    )
    bv = score_text("ignored — vector passed in", fp, vector=[1.0, 0.0, 0.0])
    assert bv.score >= 80
    assert bv.raw_positive == 1.0
    assert bv.raw_negative == 0.0


def test_score_text_low_when_aligned_with_negative_centroid():
    fp = BrandVoiceFingerprint(
        id=uuid4(),
        brand_name="X",
        positive_centroid=[1.0, 0.0, 0.0],
        negative_centroid=[0.0, 1.0, 0.0],
        embedding_model="mock",
        embedding_dim=3,
        built_at=datetime.utcnow(),
    )
    bv = score_text("ignored", fp, vector=[0.0, 1.0, 0.0])
    assert bv.score < 50
