"""Core relational records; feature workflows are intentionally absent."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, MetaData, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
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
