"""Brand voice fingerprint — centroids over on-voice and off-voice embeddings."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


class BrandVoiceFingerprint(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    brand_name: str
    positive_centroid: list[float]  # length matches the deployed model's dim
    negative_centroid: list[float]
    samples_positive: list[str] = Field(default_factory=list)
    samples_negative: list[str] = Field(default_factory=list)
    embedding_model: str = "text-embedding-3-small-alpha"
    embedding_dim: int = 1536
    built_at: datetime = Field(default_factory=datetime.utcnow)
