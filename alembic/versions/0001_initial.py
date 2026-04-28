"""initial schema (P1)

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-26
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_point", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
    )

    op.create_table(
        "briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("raw_source", sa.Text(), nullable=False),
        sa.Column("source_format", sa.String(20), nullable=False, server_default="text"),
        sa.Column("parsed_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "brief_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("field_path", sa.String(255), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "execution_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plan_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "assumption_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_plans.id"), nullable=False),
        sa.Column("field_path", sa.String(255), nullable=False),
        sa.Column("assumption_text", sa.Text(), nullable=False),
        sa.Column("basis", sa.String(30), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("created_by_agent", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "validation_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("briefs.id"), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_plans.id"), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "channel_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("spec_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "term_dictionary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("term", sa.String(255), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("synonyms", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("canonical", sa.String(255), nullable=True),
        sa.Column("rule_ref", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "brand_voice_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_name", sa.String(100), nullable=False, index=True),
        sa.Column("positive_centroid", postgresql.JSONB(), nullable=False),
        sa.Column("negative_centroid", postgresql.JSONB(), nullable=False),
        sa.Column("samples_positive", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("samples_negative", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "plan_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("derived_from_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_plans.id"), nullable=True),
        sa.Column("template_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "content_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("channel", sa.String(100), nullable=True),
        sa.Column("audience_hint", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "consistency_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_ids", postgresql.JSONB(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "trace_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("prompt_name", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("commit_hash", sa.String(40), nullable=True),
        sa.Column("tag", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    for tbl in [
        "eval_runs",
        "trace_events",
        "consistency_reports",
        "content_assets",
        "plan_templates",
        "brand_voice_fingerprints",
        "term_dictionary",
        "channel_specs",
        "validation_reports",
        "assumption_ledger",
        "execution_plans",
        "brief_overrides",
        "briefs",
        "sessions",
    ]:
        op.drop_table(tbl)
