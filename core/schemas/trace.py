"""Per-LLM-call observability event."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from .base import StrictModel


class TraceEvent(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    agent_name: str
    prompt_name: str | None = None
    prompt_version: str | None = None
    input_hash: str  # sha256 of (prompt_name + version + variables_json)
    output_size: int = 0  # bytes of serialized output
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0
    cache_hit: bool = False
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
