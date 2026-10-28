"""Core relational records; feature workflows are intentionally absent."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, MetaData, Text, UniqueConstraint, func, text
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


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint("name ~ '[^[:space:]]'", name="nonblank_name"),)
    name: Mapped[str] = mapped_column(Text)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (CheckConstraint("role IN ('owner','maintainer','member')", name="valid_role"),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app.users.id", ondelete="RESTRICT"), primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Record, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("name ~ '[^[:space:]]'", name="nonblank_name"),
        CheckConstraint("goal ~ '[^[:space:]]'", name="nonblank_goal"),
        CheckConstraint("context_revision >= 1", name="positive_context_revision"),
        CheckConstraint("jsonb_typeof(stack) = 'array'", name="stack_array"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("app.workspaces.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    stack: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    context_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    architecture_notes: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)
