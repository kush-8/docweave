from uuid import UUID
from sqlalchemy import Boolean,ForeignKey,Text
from sqlalchemy.orm import Mapped,mapped_column
from docweave.db.base import Base
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
