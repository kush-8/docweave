from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


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
