from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, Computed, Date, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


class ProviderProfile(Record, Base):
    __tablename__ = "provider_profiles"
    __table_args__ = (
        CheckConstraint("provider IN ('gemini','groq','huggingface')", name="valid_provider"),
        CheckConstraint("model ~ '[^[:space:]]' AND backend ~ '[^[:space:]]'", name="nonblank_identity"),
        CheckConstraint("role IN ('embedding','reranking','query_resolution','summarization','generation')", name="valid_role"),
        CheckConstraint("jsonb_typeof(processor_ids)='array'", name="processor_array"),
        CheckConstraint("input_usd_per_million >= 0 AND input_usd_per_million < 1000000 AND output_usd_per_million >= 0 AND output_usd_per_million < 1000000 AND fixed_usd >= 0 AND fixed_usd < 1000000", name="valid_prices"),
        CheckConstraint("max_input_tokens BETWEEN 0 AND 1000000000 AND max_output_tokens BETWEEN 0 AND 1000000000 AND max_attempts BETWEEN 1 AND 10", name="valid_bounds"),
    )
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    backend: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    processor_ids: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    input_usd_per_million: Mapped[Decimal | None] = mapped_column(Numeric())
    output_usd_per_million: Mapped[Decimal | None] = mapped_column(Numeric())
    fixed_usd: Mapped[Decimal | None] = mapped_column(Numeric())
    max_input_tokens: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    capabilities_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    account_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    pricing_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class WorkspaceAllowance(Base):
    __tablename__ = "workspace_allowances"
    __table_args__ = (
        CheckConstraint("extract(day FROM month)=1", name="month_start"),
        CheckConstraint("allowance_usd >= 0 AND allowance_usd <= 20", name="valid_allowance"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    allowance_usd: Mapped[Decimal] = mapped_column(Numeric())


class CostReservation(Record, Base):
    __tablename__ = "cost_reservations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "operation_hash", name="uq_cost_reservations_operation"),
        ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        CheckConstraint("operation_hash ~ '^[0-9a-f]{64}$'", name="valid_operation_hash"),
        CheckConstraint("extract(day FROM month)=1", name="month_start"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="valid_tokens"),
        CheckConstraint("maximum_usd >= 0 AND maximum_usd <= 1000000000000 AND (actual_usd IS NULL OR (actual_usd >= 0 AND actual_usd <= 1000000000000))", name="valid_cost"),
        CheckConstraint("status IN ('reserved','uncertain','metered') AND (status<>'metered' OR actual_usd IS NOT NULL) AND (status<>'reserved' OR actual_usd IS NULL)", name="valid_status"),
        Index("ix_cost_reservations_month", "month"),
        Index("ix_cost_reservations_workspace_month", "workspace_id", "month"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    project_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("app.provider_profiles.id", ondelete="RESTRICT"))
    operation_hash: Mapped[str] = mapped_column(Text)
    month: Mapped[date] = mapped_column(Date)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    maximum_usd: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    status: Mapped[str] = mapped_column(Text, server_default=text("'reserved'"))
    charged_usd: Mapped[Decimal] = mapped_column(Numeric(28, 12), Computed("CASE WHEN status='metered' THEN actual_usd ELSE greatest(maximum_usd,coalesce(actual_usd,0)) END", persisted=True))


class CompatibilityRequest(Base):
    __tablename__ = "compatibility_requests"
    __table_args__ = (
        CheckConstraint("operation_hash ~ '^[0-9a-f]{64}$' AND request_hash ~ '^[0-9a-f]{64}$'", name="valid_hashes"),
        CheckConstraint("input_tokens BETWEEN 0 AND 1000000000 AND output_tokens BETWEEN 0 AND 1000000000", name="valid_tokens"),
        CheckConstraint("purpose IN ('synthetic','public_fixture')", name="valid_purpose"),
    )
    operation_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("app.provider_profiles.id", ondelete="RESTRICT"))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(Text, server_default=text("'synthetic'"))


class CompatibilityOperation(Base):
    __tablename__ = "compatibility_operations"
    __table_args__ = (
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="valid_hash"),
        CheckConstraint("result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=65536)", name="bounded_result"),
    )
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey("app.cost_reservations.id", ondelete="RESTRICT"), primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
