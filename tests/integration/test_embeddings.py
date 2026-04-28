"""Embeddings integration — auto-skips cleanly when the Azure embeddings deployment
is not reachable (DeploymentNotFound / connection error / not configured)."""
from __future__ import annotations

import pytest

from core.config import get_settings
from core.embeddings.client import (
    embed_one,
    is_embeddings_available,
    probe_embeddings_deployment,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_embedding_returns_expected_dim():
    if not is_embeddings_available():
        pytest.skip("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT not set; embeddings deployment not provisioned yet.")
    if not await probe_embeddings_deployment():
        pytest.skip("Embeddings deployment is configured but not reachable yet (DeploymentNotFound).")

    vec = await embed_one("revenue teams catch at-risk accounts before churn happens")
    assert isinstance(vec, list)
    expected = get_settings().EMBEDDING_DIM
    assert len(vec) == expected, f"expected {expected}-dim vector, got {len(vec)}"
    assert all(isinstance(x, float) for x in vec[:5])
