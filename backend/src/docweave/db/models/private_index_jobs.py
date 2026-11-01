"""Durable private document/generation indexing identity."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record

class PrivateIndexJob(Record, Base):
    __tablename__ = 'private_index_jobs'
    __table_args__ = (UniqueConstraint('document_id','document_version_id','generation_id',name='uq_private_index_intent'),)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('app.documents.id',ondelete='RESTRICT'))
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey('app.document_versions.id',ondelete='RESTRICT'))
    generation_id: Mapped[UUID] = mapped_column(ForeignKey('app.index_generations.id',ondelete='RESTRICT'))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('app.users.id',ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(Text,server_default=text("'queued'"))
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    key_hash: Mapped[str | None] = mapped_column(Text)
    profile_id: Mapped[UUID | None] = mapped_column(ForeignKey('app.provider_profiles.id',ondelete='RESTRICT'))
