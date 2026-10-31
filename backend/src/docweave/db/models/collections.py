from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


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
