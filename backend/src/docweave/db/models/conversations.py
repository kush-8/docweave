from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record

class Conversation(Record,Base):
    __tablename__='conversations'
    project_id:Mapped[UUID]=mapped_column(ForeignKey('app.projects.id',ondelete='RESTRICT'))
    answer_profile_id:Mapped[UUID|None]=mapped_column(ForeignKey('app.provider_profiles.id',ondelete='RESTRICT'))
    status:Mapped[str]=mapped_column(Text,server_default='initializing')
    progress:Mapped[str|None]=mapped_column(Text)
    summary:Mapped[dict|None]=mapped_column(JSONB)
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class Turn(Record,Base):
    __tablename__='turns'
    __table_args__=(UniqueConstraint('conversation_id','idempotency_key',name='uq_turns_intent'),UniqueConstraint('conversation_id','sequence',name='uq_turns_sequence'),Index('uq_turns_active','conversation_id',unique=True,postgresql_where=text("status IN ('queued','running','waiting_for_sources')")))
    conversation_id:Mapped[UUID]=mapped_column(ForeignKey('app.conversations.id',ondelete='RESTRICT'))
    sequence:Mapped[int]=mapped_column(Integer)
    idempotency_key:Mapped[UUID]
    message:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text,server_default='queued')
    answer:Mapped[str|None]=mapped_column(Text)
    context_revision:Mapped[int|None]=mapped_column(Integer)
    required_dependencies:Mapped[list]=mapped_column(JSONB,server_default='[]')
    citations:Mapped[list]=mapped_column(JSONB,server_default='[]')
    progress:Mapped[str|None]=mapped_column(Text)

class PersonalJob(Record,Base):
    __tablename__='personal_jobs'
    conversation_id:Mapped[UUID]=mapped_column(ForeignKey('app.conversations.id',ondelete='RESTRICT'))
    turn_id:Mapped[UUID|None]=mapped_column(ForeignKey('app.turns.id',ondelete='RESTRICT'))
    actor_id:Mapped[UUID]=mapped_column(ForeignKey('app.users.id',ondelete='RESTRICT'))
    kind:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text,server_default='queued')
    lease_token:Mapped[UUID|None]
    lease_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
