"""Agent protocol — every agent has one input, one prompt, one output schema, one responsibility.

Stateless. The orchestrator graph owns state via `CampaignState`.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.state import CampaignState


@runtime_checkable
class Agent(Protocol):
    """All agents implement this interface."""

    name: str

    async def run(self, state: CampaignState) -> CampaignState:
        """Read what you need from `state`, return a new (or mutated) state."""
        ...
