"""Clarification dialog state + override application.

P4 ships a two-phase API instead of a LangGraph `interrupt` (the plan's documented fallback —
simpler, demos identically). State persists in Redis so the Streamlit rerun pattern survives
page reloads. When the user posts answers, this module:
  1. Persists each answer as a `BriefOverride` row (audit trail).
  2. Applies the answer back into the parsed Brief JSON, producing a new Brief object.
  3. Returns the updated Brief — the API layer rewrites the briefs.parsed_json column and
     the next /analyze call sees the enriched view.

The original brief raw_source is never mutated; overrides are an additive layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import redis

from core.config import get_settings
from core.schemas import Brief, Question


def _redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL)


def _dialog_key(session_id: UUID) -> str:
    return f"dialog:{session_id}"


# ---------------------------------------------------------------------------
# Dialog persistence
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DialogState:
    session_id: UUID
    brief_id: UUID
    questions: list[Question]
    answers: dict[str, str]  # question_id (str) -> answer string
    completed: bool = False


def save_dialog(state: DialogState, ttl: int = 3600) -> None:
    payload = {
        "session_id": str(state.session_id),
        "brief_id": str(state.brief_id),
        "questions": [q.model_dump(mode="json") for q in state.questions],
        "answers": state.answers,
        "completed": state.completed,
    }
    _redis().setex(_dialog_key(state.session_id), ttl, json.dumps(payload, default=str))


def load_dialog(session_id: UUID) -> DialogState | None:
    raw = _redis().get(_dialog_key(session_id))
    if raw is None:
        return None
    data = json.loads(raw.decode("utf-8"))
    return DialogState(
        session_id=UUID(data["session_id"]),
        brief_id=UUID(data["brief_id"]),
        questions=[Question.model_validate(q) for q in data.get("questions", [])],
        answers=data.get("answers", {}),
        completed=data.get("completed", False),
    )


def clear_dialog(session_id: UUID) -> None:
    _redis().delete(_dialog_key(session_id))


# ---------------------------------------------------------------------------
# Override application
# ---------------------------------------------------------------------------


def apply_overrides_to_brief(brief: Brief, overrides: dict[str, str]) -> Brief:
    """Return a new Brief with each `(field_path, value)` written into the right slot.

    Supports a small set of dotted paths sufficient for Tier 0:
      - `budget.total`                 → numeric
      - `budget.per_channel`           → JSON dict (or pass-through prose)
      - `timeline.launch_date`         → ISO date
      - `timeline.asset_lock_date`     → ISO date
      - `target_audience.raw_description`
      - `key_message`
      - `business_objective`
      - `channels`                     → comma-separated names → list[ChannelRef]
      - `constraints.tone_guidelines`
      - any other field_path → appended to constraints.mandatory_inclusions as fallback.

    Unknown paths fall through gracefully (no exception) — the value is captured in
    `BriefOverride` rows by the caller for audit.
    """
    data = brief.model_dump(mode="python")

    for path, value in overrides.items():
        if not value or not str(value).strip():
            continue
        v = str(value).strip()
        try:
            _set_path(data, path, v)
        except Exception:
            # Don't let one bad override blow up the whole apply — the audit row still landed.
            data.setdefault("constraints", {}).setdefault("mandatory_inclusions", []).append(
                f"[override:{path}] {v}"
            )

    # Ensure types Pydantic expects (e.g. Decimal) re-coerce cleanly.
    return Brief.model_validate(data)


def _set_path(data: dict[str, Any], path: str, value: str) -> None:
    parts = path.split(".")

    def _budget_dict() -> dict:
        # `budget` field is Optional[BudgetAllocation], so the dict value may be None or
        # a dict. setdefault() does NOT overwrite None — must do so explicitly.
        existing = data.get("budget")
        if not isinstance(existing, dict):
            existing = {}
            data["budget"] = existing
        return existing

    if path == "budget.total":
        _budget_dict()["total"] = Decimal(value.replace(",", "").replace("$", "").strip() or "0")
        return
    if path == "budget.per_channel":
        # Accept JSON dict OR comma list "LinkedIn:40000,Email:10000"
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                _budget_dict()["per_channel"] = {k: Decimal(str(v)) for k, v in parsed.items()}
                return
        except Exception:
            pass
        per_channel: dict[str, Decimal] = {}
        for chunk in value.split(","):
            if ":" in chunk:
                k, v = chunk.split(":", 1)
                try:
                    per_channel[k.strip()] = Decimal(v.strip().replace(",", "").replace("$", ""))
                except Exception:
                    continue
        if per_channel:
            _budget_dict()["per_channel"] = per_channel
        return
    if path in ("timeline.launch_date", "timeline.asset_lock_date"):
        data.setdefault("timeline", {})[parts[1]] = value  # ISO string; Pydantic parses
        return
    if path == "channels":
        items = [c.strip() for c in value.split(",") if c.strip()]
        # Pydantic v2 will accept a list of dicts via model_validate
        data["channels"] = [{"name": name} for name in items]
        return
    if path == "target_audience.raw_description":
        data.setdefault("target_audience", {})["raw_description"] = value
        return
    if path == "constraints.tone_guidelines":
        data.setdefault("constraints", {})["tone_guidelines"] = value
        return

    # Generic dotted-path fallback (works for top-level scalars like `key_message`,
    # `business_objective`). Unknown top-level fields raise so the caller routes the
    # value to constraints.mandatory_inclusions as audit (never corrupt the Brief shape).
    valid_top_level = set(Brief.model_fields.keys())
    if parts[0] not in valid_top_level:
        raise KeyError(f"unknown brief field: {path}")
    cursor = data
    for p in parts[:-1]:
        cursor = cursor.setdefault(p, {})
    cursor[parts[-1]] = value
