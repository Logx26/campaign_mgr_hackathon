"""Typed application configuration loaded from environment.

All env vars are declared here. No other module reads `os.environ` directly.
"""
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: SecretStr
    AZURE_OPENAI_ENDPOINT: str  # must end with trailing slash
    AZURE_OPENAI_DEPLOYMENT: str
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"

    # Storage
    POSTGRES_DSN: str = "postgresql+psycopg://hackuser:hackpass@localhost:5432/hackdb"
    QDRANT_URL: str = "http://localhost:6333"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Caching + cost
    LLM_CACHE_TTL_SECONDS: int = 3600
    SESSION_BUDGET_USD: Decimal = Decimal("1.00")

    # App
    APP_ENV: Literal["dev", "demo", "test"] = "dev"

    # Embeddings — defaults to text-embedding-3-small (1536-dim) per the provisioned deployment.
    # If switched to text-embedding-3-large, set EMBEDDING_DIM=3072 in .env AND drop/recreate
    # the Qdrant collections (their dim is fixed at create time).
    EMBEDDING_DIM: int = 1536

    # API
    API_BASE_URL: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Use this everywhere — never instantiate Settings directly."""
    return Settings()  # type: ignore[call-arg]
