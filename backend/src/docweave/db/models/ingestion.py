from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


class DocumentationSelection(Record, Base):
    __tablename__ = "documentation_selections"
    __table_args__ = (ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        CheckConstraint("(project_id IS NOT NULL AND catalog_revision_id IS NULL) OR (project_id IS NULL AND workspace_id IS NULL AND catalog_revision_id IS NOT NULL AND approved_stack IS NULL)", name="exact_parent"),)
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.projects.id", ondelete="RESTRICT", name="fk_documentation_selections_project_id_direct"))
    catalog_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.public_catalog_revisions.id", ondelete="RESTRICT"))
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
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(ForeignKey("app.collections.id", ondelete="RESTRICT", name="fk_sources_collection_id_direct"))
    source_selection_id: Mapped[UUID] = mapped_column(ForeignKey("app.documentation_selections.id", ondelete="RESTRICT"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Record, Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"),
    )
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(ForeignKey("app.collections.id", ondelete="RESTRICT", name="fk_documents_collection_id_direct"))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.sources.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'quarantined'"))
    active_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.document_versions.id", ondelete="RESTRICT", use_alter=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Record, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("document_id", "content_hash", "configuration", name="uq_document_versions_content"),
    )
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("app.documents.id", ondelete="RESTRICT", name="fk_document_versions_document_id_direct"))
    content_hash: Mapped[str] = mapped_column(Text)
    configuration: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class IngestionJob(Record, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),)
    workspace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("app.documents.id", ondelete="RESTRICT", name="fk_ingestion_jobs_document_id_direct"))
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
