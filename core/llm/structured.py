"""Helpers for binding Pydantic schemas to Azure OpenAI Structured Outputs (json_schema mode)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def schema_for_response_format(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Produce the Azure response_format payload for a Pydantic model.

    Azure `2024-08-01-preview` strict mode requires:
      - additionalProperties: false on every object
      - all properties listed in `required`
      - top-level wrapper {type:'json_schema', json_schema:{name,schema,strict:true}}
    """
    schema = _strictify(model_cls.model_json_schema())
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model_cls.__name__,
            "schema": schema,
            "strict": True,
        },
    }


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Walk a JSON-schema dict and force strict-mode constraints."""
    if not isinstance(schema, dict):
        return schema

    # Copy to avoid mutating Pydantic's cache
    out: dict[str, Any] = dict(schema)

    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        props = out.get("properties", {}) or {}
        if props:
            # Azure strict mode demands EVERY property in `required`. Pydantic by default
            # only lists the truly-required ones (skipping fields with defaults), which
            # 400s with "required is required to be supplied and to be an array including
            # every key in properties". Force overwrite.
            out["required"] = list(props.keys())
        out["properties"] = {k: _strictify(v) for k, v in props.items()}

    for nested_key in ("anyOf", "oneOf", "allOf"):
        if nested_key in out and isinstance(out[nested_key], list):
            out[nested_key] = [_strictify(s) for s in out[nested_key]]

    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _strictify(out["items"])

    if "$defs" in out and isinstance(out["$defs"], dict):
        out["$defs"] = {k: _strictify(v) for k, v in out["$defs"].items()}
    if "definitions" in out and isinstance(out["definitions"], dict):
        out["definitions"] = {k: _strictify(v) for k, v in out["definitions"].items()}

    return out
