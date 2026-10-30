"""Core relational records; feature workflows are intentionally absent."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, MetaData, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="app", naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
    })


class Record:
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        CheckConstraint("issuer ~ '[^[:space:]]'", name="nonblank_issuer"),
        CheckConstraint("subject ~ '[^[:space:]]'", name="nonblank_subject"),
        CheckConstraint("display_name ~ '[^[:space:]]'", name="nonblank_display_name"),
    )
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class AuthFlow(Base):
    __tablename__ = "auth_flows"
    state_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    browser_hash: Mapped[str] = mapped_column(Text, index=True)
    encrypted_data: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="CASCADE"))
    encrypted_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    resets_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint("name ~ '[^[:space:]]'", name="nonblank_name"),)
    name: Mapped[str] = mapped_column(Text)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (CheckConstraint("role IN ('owner','maintainer','member')", name="valid_role"),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Record, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        CheckConstraint("role IN ('owner','maintainer','member')", name="valid_role"),
        CheckConstraint("email ~ '[^[:space:]]'", name="nonblank_email"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="valid_token_hash"),
        CheckConstraint("NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)", name="one_terminal_state"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Project(Record, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_projects_id_workspace_id"),
        CheckConstraint("name ~ '[^[:space:]]'", name="nonblank_name"),
        CheckConstraint("goal ~ '[^[:space:]]'", name="nonblank_goal"),
        CheckConstraint("context_revision >= 1", name="positive_context_revision"),
        CheckConstraint("processing_revision >= 1", name="positive_processing_revision"),
        CheckConstraint("jsonb_typeof(stack) = 'array'", name="stack_array"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    stack: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    context_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    processing_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    architecture_notes: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)


class Collection(Record, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_collections_id_workspace_id"),
        ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        CheckConstraint("name ~ '[^[:space:]]'", name="nonblank_name"),
        CheckConstraint("grant_revision >= 1", name="positive_grant_revision"),
        CheckConstraint("processing_revision >= 1", name="positive_processing_revision"),
        Index("uq_collections_default_project", "project_id", unique=True, postgresql_where=text("is_default")),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    grant_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    processing_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class CollectionGrant(Base):
    __tablename__ = "collection_grants"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["workspace_id", "user_id"], ["app.memberships.workspace_id", "app.memberships.user_id"], ondelete="CASCADE"),
        CheckConstraint("access IN ('read','write')", name="valid_access"),
        Index("ix_collection_grants_membership", "workspace_id", "user_id"),
    )
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    access: Mapped[str] = mapped_column(Text)


class Processor(Base):
    __tablename__ = "processors"
    __table_args__ = (
        CheckConstraint("id ~ '[^[:space:]]' AND backend ~ '[^[:space:]]'", name="nonblank_identity"),
        CheckConstraint("provider IN ('gemini','groq','huggingface')", name="valid_provider"),
        CheckConstraint("jsonb_typeof(roles)='array' AND jsonb_array_length(roles)>0 AND roles <@ '[\"embedding\",\"reranking\",\"query_resolution\",\"summarization\",\"generation\"]'::jsonb", name="valid_roles"),
    )
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    backend: Mapped[str] = mapped_column(Text)
    roles: Mapped[list] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ProjectProcessorApproval(Base):
    __tablename__ = "project_processor_approvals"
    __table_args__ = (ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    processor_id: Mapped[str] = mapped_column(ForeignKey("app.processors.id", ondelete="RESTRICT"), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CollectionProcessorApproval(Base):
    __tablename__ = "collection_processor_approvals"
    __table_args__ = (ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),)
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    processor_id: Mapped[str] = mapped_column(ForeignKey("app.processors.id", ondelete="RESTRICT"), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationRequest(Record, Base):
    __tablename__ = "documentation_requests"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        CheckConstraint("state IN ('pending_review','superseded')", name="valid_state"),
        CheckConstraint("context_revision >= 1", name="positive_context_revision"),
        CheckConstraint("reason IN ('version_unresolved','source_catalog_unavailable')", name="valid_reason"),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    context_revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)


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


class DocumentationSelection(Record, Base):
    __tablename__ = "documentation_selections"
    __table_args__ = (ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    technology: Mapped[str] = mapped_column(Text)
    docs_target: Mapped[str] = mapped_column(Text)
    coverage: Mapped[dict] = mapped_column(JSONB)
    source_url: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    path_prefix: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    approved_stack: Mapped[dict | None] = mapped_column(JSONB)


class Source(Record, Base):
    __tablename__ = "sources"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("collection_id", "source_selection_id", name="uq_sources_selection"),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    source_selection_id: Mapped[UUID] = mapped_column(ForeignKey("app.documentation_selections.id", ondelete="RESTRICT"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Record, Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.sources.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'quarantined'"))
    active_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Record, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("document_id", "content_hash", "configuration", name="uq_document_versions_content"),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    content_hash: Mapped[str] = mapped_column(Text)
    configuration: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class IngestionJob(Record, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    configuration: Mapped[str] = mapped_column(Text)
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    stage: Mapped[str] = mapped_column(Text, server_default=text("'quarantined'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    retryable: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    lease_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexGeneration(Record, Base):
    __tablename__ = "index_generations"
    __table_args__ = (
        CheckConstraint("dimensions=768 AND normalization='unit-l2'", name="supported_vectors"),
        CheckConstraint("jsonb_typeof(processor_ids)='array' AND jsonb_array_length(processor_ids)>0", name="processor_array"),
    )
    model: Mapped[str] = mapped_column(Text)
    backend: Mapped[str] = mapped_column(Text)
    dimensions: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(Text)
    chunker: Mapped[str] = mapped_column(Text)
    processor_ids: Mapped[list] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class DocumentIndex(Base):
    __tablename__ = "document_indexes"
    __table_args__ = (ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),)
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    generation_id: Mapped[UUID] = mapped_column(ForeignKey("app.index_generations.id", ondelete="RESTRICT"), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("app.document_versions.id", ondelete="RESTRICT"))


class Chunk(Record, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("document_version_id", "generation_id", "start_offset", name="uq_chunks_span_generation"),
        CheckConstraint("start_offset>=0 AND end_offset>start_offset AND char_length(content)=end_offset-start_offset", name="exact_span"),
        CheckConstraint("line_start>=1 AND line_end>=line_start AND token_count>=0", name="valid_locator"),
        CheckConstraint("public.vector_norm(embedding) BETWEEN 0.9999 AND 1.0001", name="unit_embedding"),
        Index("ix_chunks_scope", "workspace_id", "project_id", "collection_id", "generation_id", "document_version_id"),
        Index("ix_chunks_search", "search", postgresql_using="gin"),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64}),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("app.document_versions.id", ondelete="RESTRICT"))
    generation_id: Mapped[UUID] = mapped_column(ForeignKey("app.index_generations.id", ondelete="RESTRICT"))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    terms: Mapped[dict] = mapped_column(JSONB)
    token_count: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict] = mapped_column(JSONB)
    search: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english'::regconfig,content)", persisted=True))
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768))
