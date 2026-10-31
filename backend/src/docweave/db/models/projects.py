from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


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
