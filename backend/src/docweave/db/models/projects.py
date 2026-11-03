from uuid import UUID
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
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
        CheckConstraint("jsonb_typeof(documentation_exclusions)='array'", name="documentation_exclusions_array"),
        CheckConstraint("repository_id > 0", name="positive_repository_id"),
    )
    workspace_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), index=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"), index=True)
    repository_id: Mapped[int | None] = mapped_column(BigInteger)
    repository_branch: Mapped[str | None] = mapped_column(Text)
    application_path: Mapped[str | None] = mapped_column(Text)
    last_commit_sha: Mapped[str | None] = mapped_column(Text)
    stack_fingerprint: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(Text, server_default=text("'repository_required'"))
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    stack: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    documentation_exclusions: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    context_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    processing_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    architecture_notes: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)
