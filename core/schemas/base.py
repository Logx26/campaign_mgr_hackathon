"""Shared Pydantic base for all typed IO objects.

`extra='forbid'` is mandatory for Azure OpenAI Structured Outputs (json_schema with strict=True).
"""
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for every schema bound to LLM structured output or persisted to JSONB."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
        ser_json_timedelta="iso8601",
    )
