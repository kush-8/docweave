from uuid import UUID
from datetime import datetime
from sqlalchemy import BigInteger,Boolean,CheckConstraint,DateTime,ForeignKey,Integer,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from docweave.db.base import Base,Record
class DocumentAssessment(Base):
    __tablename__='document_assessments'
    document_version_id:Mapped[UUID]=mapped_column(ForeignKey('app.document_versions.id',ondelete='RESTRICT'),primary_key=True)
    content_hash:Mapped[str]=mapped_column(Text)
    parser_config_hash:Mapped[str]=mapped_column(Text)
    rule_revision:Mapped[str]=mapped_column(Text)
    credential_blocked:Mapped[bool]=mapped_column(Boolean)
    injection_flagged:Mapped[bool]=mapped_column(Boolean)
    complete:Mapped[bool]=mapped_column(Boolean)
    reviewed_by:Mapped[UUID|None]=mapped_column(ForeignKey('app.users.id',ondelete='RESTRICT'))
    policy_epoch:Mapped[int]=mapped_column(BigInteger,server_default='0')
    findings:Mapped[list]=mapped_column(JSONB,server_default='[]')

class GuardrailPolicy(Base):
    __tablename__='guardrail_policy'
    __table_args__=(CheckConstraint('id=1',name='singleton'),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    rule_revision:Mapped[str]=mapped_column(Text)
    epoch:Mapped[int]=mapped_column(BigInteger)

class GuardrailRescan(Record,Base):
    __tablename__='guardrail_rescans'
    __table_args__=(UniqueConstraint('document_version_id','epoch',name='uq_guardrail_rescan_epoch'),)
    document_version_id:Mapped[UUID]=mapped_column(ForeignKey('app.document_versions.id',ondelete='RESTRICT'))
    epoch:Mapped[int]=mapped_column(BigInteger)
    rule_revision:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text,server_default='queued')
    lease_token:Mapped[UUID|None]
    lease_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class GuardrailEvent(Record,Base):
    __tablename__='guardrail_events'
    document_version_id:Mapped[UUID|None]=mapped_column(ForeignKey('app.document_versions.id',ondelete='RESTRICT'))
    epoch:Mapped[int]=mapped_column(BigInteger)
    rule_revision:Mapped[str]=mapped_column(Text)
    kind:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[UUID|None]=mapped_column(ForeignKey('app.users.id',ondelete='RESTRICT'))
    findings:Mapped[list]=mapped_column(JSONB,server_default='[]')
