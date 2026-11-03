from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
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
