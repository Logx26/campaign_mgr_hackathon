"""SQLAlchemy ORM models — the structured store.

Every table uses a UUID primary key. JSONB is used for plan/brief/report bodies; structured
fields are pulled out as columns when they need indexing or FK references.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Sessions & Briefs
# ---------------------------------------------------------------------------


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    entry_point: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(30), default="active")


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )
    raw_source: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(String(20), default="text")
    parsed_json: Mapped[dict] = mapped_column(JSONB)  # full Brief Pydantic model
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    overrides: Mapped[list["BriefOverride"]] = relationship(back_populates="brief", cascade="all, delete-orphan")


class BriefOverride(Base):
    __tablename__ = "brief_overrides"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    brief_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("briefs.id"))
    field_path: Mapped[str] = mapped_column(String(255))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    brief: Mapped["Brief"] = relationship(back_populates="overrides")


# ---------------------------------------------------------------------------
# Plans, ledgers, validation
# ---------------------------------------------------------------------------


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    brief_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("briefs.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_json: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssumptionLedger(Base):
    __tablename__ = "assumption_ledger"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("execution_plans.id"))
    field_path: Mapped[str] = mapped_column(String(255))
    assumption_text: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(30))  # user_input | rule | exemplar | llm_inference
    citation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    created_by_agent: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ValidationReport(Base):
    __tablename__ = "validation_reports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    brief_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("briefs.id"))
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("execution_plans.id"))
    report_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Knowledge layer (seeded + editable)
# ---------------------------------------------------------------------------


class ChannelSpec(Base):
    __tablename__ = "channel_specs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    spec_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TermDictionaryEntry(Base):
    __tablename__ = "term_dictionary"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    term: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[str] = mapped_column(String(20))  # approved | prohibited
    synonyms: Mapped[list] = mapped_column(JSONB, default=list)
    canonical: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rule_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BrandVoiceFingerprint(Base):
    __tablename__ = "brand_voice_fingerprints"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    brand_name: Mapped[str] = mapped_column(String(100), index=True)
    positive_centroid: Mapped[list] = mapped_column(JSONB)  # list[float]
    negative_centroid: Mapped[list] = mapped_column(JSONB)
    samples_positive: Mapped[list] = mapped_column(JSONB, default=list)
    samples_negative: Mapped[list] = mapped_column(JSONB, default=list)
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding_dim: Mapped[int] = mapped_column(Integer)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlanTemplate(Base):
    __tablename__ = "plan_templates"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    derived_from_plan_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("execution_plans.id"), nullable=True
    )
    template_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Content assets (W3) + consistency reports
# ---------------------------------------------------------------------------


class ContentAsset(Base):
    __tablename__ = "content_assets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audience_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # qdrant point id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConsistencyReport(Base):
    __tablename__ = "consistency_reports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_ids: Mapped[list] = mapped_column(JSONB)  # list of UUID strings
    report_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Observability + eval
# ---------------------------------------------------------------------------


class TraceEvent(Base):
    __tablename__ = "trace_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    prompt_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    output_size: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metrics: Mapped[dict] = mapped_column(JSONB)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
