from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from docweave.db.base import Base, Record


class PublicCatalogRevision(Record, Base):
    __tablename__ = 'public_catalog_revisions'
    __table_args__ = (
        CheckConstraint("technology ~ '[^[:space:]]' AND docs_target ~ '[^[:space:]]'", name='nonblank_identity'),
        CheckConstraint("ecosystem IN ('python','javascript')", name='valid_ecosystem'),
        CheckConstraint("jsonb_typeof(coverage)='object' AND coalesce(coverage->>'granularity','') IN ('exact','major','minor') AND jsonb_typeof(coverage->'version')='string' AND coalesce(coverage->>'version','') ~ '[^[:space:]]'", name='valid_coverage'),
        CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name='valid_source_hash'),
    )
    technology: Mapped[str] = mapped_column(Text)
    ecosystem: Mapped[str] = mapped_column(Text)
    docs_target: Mapped[str] = mapped_column(Text)
    coverage: Mapped[dict] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(Text)
    path_prefix: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    source_approved: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))


class ProjectCatalogSelection(Record, Base):
    __tablename__ = 'project_catalog_selections'
    __table_args__ = (
        UniqueConstraint('project_id', 'dependency_id', name='uq_project_catalog_selections_dependency'),
        CheckConstraint("dependency_id ~ '[^[:space:]]'", name='nonblank_dependency'),
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey('app.projects.id', ondelete='RESTRICT'))
    dependency_id: Mapped[str] = mapped_column(Text)
    catalog_revision_id: Mapped[UUID] = mapped_column(ForeignKey('app.public_catalog_revisions.id', ondelete='RESTRICT'))
    fallback_accepted: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
