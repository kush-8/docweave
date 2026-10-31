from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from docweave.db.base import Base,Record
class CatalogJob(Record,Base):
    __tablename__='catalog_jobs'
    __table_args__=(UniqueConstraint('catalog_revision_id','generation_id',name='uq_catalog_jobs_revision_generation'),)
    catalog_revision_id:Mapped[UUID]=mapped_column(ForeignKey('app.public_catalog_revisions.id',ondelete='RESTRICT'))
    generation_id:Mapped[UUID]=mapped_column(ForeignKey('app.index_generations.id',ondelete='RESTRICT'))
    document_id:Mapped[UUID|None]=mapped_column(ForeignKey('app.documents.id',ondelete='RESTRICT'))
    status:Mapped[str]=mapped_column(Text,server_default='queued')
    stage:Mapped[str]=mapped_column(Text,server_default='queued')
    lease_token:Mapped[UUID|None]
    lease_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
