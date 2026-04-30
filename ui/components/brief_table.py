"""Brief → table rows mapper. One source of truth for the structured-brief renderer
shared by Page 1 (Plan from Brief) and Page 2 (Plan QA).

Status logic consults the latest GapList: if a gap exists with a `field_path` that
matches the row's source path, the auto-derived status is overridden to "gap". This
keeps the table honest — e.g. `target_audience.raw_description` doesn't show
"Confirmed" when the audience is too vague and the completeness rule fired.

The mapping deliberately strips `[override:*]` audit prefixes from
`constraints.mandatory_inclusions` rows for display only; the storage value keeps the
audit prefix per ADR-008.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from ui.styles import scrub_override_prefix


@dataclass(frozen=True)
class BriefRow:
    field: str           # human label
    value: str           # rendered value (HTML-safe plain text)
    status: str          # "confirmed" | "inferred" | "gap" | "missing" | "neutral"
    source_path: str     # dotted path used to match against GapList.field_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VAGUE_CHANNEL_NAMES = {"social", "performance", "digital", "online", "channels"}


def _gap_paths(gaps: dict | None) -> set[str]:
    if not gaps or not isinstance(gaps, dict):
        return set()
    out: set[str] = set()
    for g in gaps.get("gaps", []) or []:
        if isinstance(g, dict) and g.get("field_path"):
            out.add(str(g["field_path"]))
    return out


def _status_for(path: str, *, derived: str, gap_paths: set[str]) -> str:
    """If a gap targets `path` (or a parent), force status to gap."""
    for gp in gap_paths:
        if gp == path or path.startswith(gp + ".") or gp.startswith(path + "."):
            return "gap"
    return derived


def _fmt_money(amount, currency: str = "USD") -> str:
    if amount is None:
        return "—"
    try:
        as_dec = Decimal(str(amount))
        if as_dec == as_dec.to_integral_value():
            return f"{currency} {as_dec:,.0f}"
        return f"{currency} {as_dec:,.2f}"
    except Exception:
        return f"{currency} {amount}"


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) > 0
    return bool(v)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def brief_to_rows(
    brief: dict,
    *,
    gaps: dict | None = None,
) -> list[BriefRow]:
    """Map a Brief (dict from `Brief.model_dump`) into table rows.

    `gaps` is the latest `GapList` dict (as returned by `/briefs/{id}/analyze`); pass
    `None` to skip the status-override pass."""
    if not isinstance(brief, dict):
        return []
    gp = _gap_paths(gaps)

    rows: list[BriefRow] = []

    # ---- Identity --------------------------------------------------------
    name = (brief.get("campaign_name") or "").strip()
    rows.append(
        BriefRow(
            field="Campaign name",
            value=name or "—",
            status=_status_for(
                "campaign_name",
                derived="confirmed" if name else "missing",
                gap_paths=gp,
            ),
            source_path="campaign_name",
        )
    )

    obj = (brief.get("business_objective") or "").strip()
    rows.append(
        BriefRow(
            field="Business objective",
            value=obj or "—",
            status=_status_for(
                "business_objective",
                derived="confirmed" if obj else "missing",
                gap_paths=gp,
            ),
            source_path="business_objective",
        )
    )

    key_msg = (brief.get("key_message") or "").strip()
    rows.append(
        BriefRow(
            field="Key message",
            value=key_msg or "—",
            status=_status_for(
                "key_message",
                derived="confirmed" if key_msg else "gap",
                gap_paths=gp,
            ),
            source_path="key_message",
        )
    )

    # ---- Audience --------------------------------------------------------
    audience = brief.get("target_audience") or {}
    audience_text = (audience.get("raw_description") or "").strip()
    rows.append(
        BriefRow(
            field="Target audience",
            value=audience_text or "—",
            status=_status_for(
                "target_audience.raw_description",
                derived="confirmed" if audience_text else "missing",
                gap_paths=gp,
            ),
            source_path="target_audience.raw_description",
        )
    )

    # ---- Channels --------------------------------------------------------
    channels = brief.get("channels") or []
    if channels:
        names = [str((c or {}).get("name") or "").strip() for c in channels if isinstance(c, dict)]
        names = [n for n in names if n]
        vague = any(n.lower() in _VAGUE_CHANNEL_NAMES for n in names)
        rows.append(
            BriefRow(
                field="Channels",
                value=", ".join(names) if names else "—",
                status=_status_for(
                    "channels",
                    derived="gap" if vague or not names else "confirmed",
                    gap_paths=gp,
                ),
                source_path="channels",
            )
        )
    else:
        rows.append(
            BriefRow(
                field="Channels",
                value="—",
                status=_status_for("channels", derived="missing", gap_paths=gp),
                source_path="channels",
            )
        )

    # ---- Budget ----------------------------------------------------------
    budget = brief.get("budget") or {}
    if budget:
        currency = budget.get("currency") or "USD"
        total = budget.get("total")
        rows.append(
            BriefRow(
                field="Budget — total",
                value=_fmt_money(total, currency),
                status=_status_for(
                    "budget.total",
                    derived="confirmed" if _truthy(total) else "missing",
                    gap_paths=gp,
                ),
                source_path="budget.total",
            )
        )
        per_channel = budget.get("per_channel") or {}
        if per_channel:
            for ch_name, amount in per_channel.items():
                rows.append(
                    BriefRow(
                        field=f"Budget — {ch_name}",
                        value=_fmt_money(amount, currency),
                        status=_status_for(
                            f"budget.per_channel.{ch_name}",
                            derived="confirmed" if _truthy(amount) else "missing",
                            gap_paths=gp,
                        ),
                        source_path=f"budget.per_channel.{ch_name}",
                    )
                )
    else:
        rows.append(
            BriefRow(
                field="Budget — total",
                value="—",
                status=_status_for("budget.total", derived="missing", gap_paths=gp),
                source_path="budget.total",
            )
        )

    # ---- Timeline --------------------------------------------------------
    timeline = brief.get("timeline") or {}
    launch_date = timeline.get("launch_date")
    rows.append(
        BriefRow(
            field="Timeline — launch date",
            value=str(launch_date) if launch_date else "—",
            status=_status_for(
                "timeline.launch_date",
                derived="confirmed" if launch_date else "missing",
                gap_paths=gp,
            ),
            source_path="timeline.launch_date",
        )
    )
    asset_lock = timeline.get("asset_lock_date")
    rows.append(
        BriefRow(
            field="Timeline — asset lock",
            value=str(asset_lock) if asset_lock else "—",
            status=_status_for(
                "timeline.asset_lock_date",
                derived="confirmed" if asset_lock else "missing",
                gap_paths=gp,
            ),
            source_path="timeline.asset_lock_date",
        )
    )

    # ---- Quantified targets ---------------------------------------------
    targets = brief.get("quantified_targets") or []
    if targets:
        for i, t in enumerate(targets):
            if not isinstance(t, dict):
                continue
            metric = t.get("metric_name") or "(metric)"
            tgt = t.get("target")
            base = t.get("baseline")
            unit = t.get("unit") or ""
            arrow = f"{base} → {tgt} {unit}".strip() if base is not None else f"{tgt} {unit}".strip()
            rows.append(
                BriefRow(
                    field=f"Quantified target — {metric}",
                    value=arrow.strip(),
                    status=_status_for(
                        f"quantified_targets.{i}",
                        derived="confirmed",
                        gap_paths=gp,
                    ),
                    source_path=f"quantified_targets.{i}",
                )
            )
    else:
        rows.append(
            BriefRow(
                field="Quantified targets",
                value="—",
                status=_status_for(
                    "quantified_targets",
                    derived="gap",
                    gap_paths=gp,
                ),
                source_path="quantified_targets",
            )
        )

    # ---- Success metrics ------------------------------------------------
    metrics = brief.get("success_metrics") or []
    if metrics:
        for i, m in enumerate(metrics):
            if not isinstance(m, dict):
                continue
            mname = m.get("name") or "(metric)"
            target = m.get("target")
            base = m.get("baseline")
            unit = m.get("unit") or ""
            if target is not None:
                value = f"{base} → {target} {unit}".strip() if base is not None else f"{target} {unit}".strip()
            else:
                value = "(no target)"
            rows.append(
                BriefRow(
                    field=f"Success metric — {mname}",
                    value=value,
                    status=_status_for(
                        f"success_metrics.{i}",
                        derived="confirmed" if target is not None else "gap",
                        gap_paths=gp,
                    ),
                    source_path=f"success_metrics.{i}",
                )
            )
    else:
        rows.append(
            BriefRow(
                field="Success metrics",
                value="—",
                status=_status_for(
                    "success_metrics",
                    derived="gap",
                    gap_paths=gp,
                ),
                source_path="success_metrics",
            )
        )

    # ---- Constraints -----------------------------------------------------
    constraints = brief.get("constraints") or {}
    tone = (constraints.get("tone_guidelines") or "").strip()
    rows.append(
        BriefRow(
            field="Tone guidelines",
            value=tone or "—",
            status=_status_for(
                "constraints.tone_guidelines",
                derived="inferred" if tone else "missing",
                gap_paths=gp,
            ),
            source_path="constraints.tone_guidelines",
        )
    )

    inclusions = constraints.get("mandatory_inclusions") or []
    for i, item in enumerate(inclusions):
        if not isinstance(item, str):
            continue
        rows.append(
            BriefRow(
                field=f"Mandatory inclusion #{i + 1}",
                value=scrub_override_prefix(item),
                status=_status_for(
                    f"constraints.mandatory_inclusions.{i}",
                    derived="confirmed",
                    gap_paths=gp,
                ),
                source_path=f"constraints.mandatory_inclusions.{i}",
            )
        )

    exclusions = constraints.get("exclusions") or []
    for i, item in enumerate(exclusions):
        if not isinstance(item, str):
            continue
        rows.append(
            BriefRow(
                field=f"Exclusion #{i + 1}",
                value=scrub_override_prefix(item),
                status=_status_for(
                    f"constraints.exclusions.{i}",
                    derived="confirmed",
                    gap_paths=gp,
                ),
                source_path=f"constraints.exclusions.{i}",
            )
        )

    legal = constraints.get("legal_restrictions") or []
    for i, item in enumerate(legal):
        if not isinstance(item, str):
            continue
        rows.append(
            BriefRow(
                field=f"Legal restriction #{i + 1}",
                value=scrub_override_prefix(item),
                status=_status_for(
                    f"constraints.legal_restrictions.{i}",
                    derived="confirmed",
                    gap_paths=gp,
                ),
                source_path=f"constraints.legal_restrictions.{i}",
            )
        )

    # ---- Source format --------------------------------------------------
    rows.append(
        BriefRow(
            field="Source format",
            value=str(brief.get("source_format") or "text"),
            status="confirmed",
            source_path="source_format",
        )
    )

    return rows


def rows_as_table_input(rows: Sequence[BriefRow]) -> Iterable[tuple[str, str, str]]:
    """Convenience: convert BriefRow → tuples consumable by `key_value_table`."""
    return [(r.field, r.value, r.status) for r in rows]
