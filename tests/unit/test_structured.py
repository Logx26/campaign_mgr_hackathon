"""structured.schema_for_response_format produces strict-mode-compatible payloads."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from core.llm.structured import schema_for_response_format


class _Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    count: int


class _Outer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    inner: _Inner


def test_top_level_wrapper_shape():
    payload = schema_for_response_format(_Outer)
    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["name"] == "_Outer"
    assert payload["json_schema"]["strict"] is True


def test_object_nodes_have_additional_properties_false():
    payload = schema_for_response_format(_Outer)
    schema = payload["json_schema"]["schema"]
    assert schema.get("additionalProperties") is False
    inner_def = schema.get("$defs", {}).get("_Inner") or schema["properties"]["inner"]
    assert inner_def.get("additionalProperties") is False


def test_required_filled_when_missing():
    payload = schema_for_response_format(_Inner)
    schema = payload["json_schema"]["schema"]
    assert set(schema.get("required", [])) == {"name", "count"}


def test_required_includes_optional_fields_for_strict_mode():
    """Azure strict mode demands EVERY property in `required`, including ones
    Pydantic considers optional (those with defaults). The strictifier must overwrite."""
    from pydantic import Field

    class _WithOptional(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str
        tags: list[str] = Field(default_factory=list)  # optional in Pydantic; required in strict mode

    payload = schema_for_response_format(_WithOptional)
    required = set(payload["json_schema"]["schema"]["required"])
    assert required == {"name", "tags"}
