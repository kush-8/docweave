from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, Computed, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base, Record


class IndexGeneration(Record, Base):
    __tablename__ = "index_generations"
    __table_args__ = (
        CheckConstraint("dimensions=768 AND normalization='unit-l2'", name="supported_vectors"),
        CheckConstraint("jsonb_typeof(processor_ids)='array' AND jsonb_array_length(processor_ids)>0", name="processor_array"),
    )
    model: Mapped[str] = mapped_column(Text)
    backend: Mapped[str] = mapped_column(Text)
    dimensions: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(Text)
    chunker: Mapped[str] = mapped_column(Text)
    processor_ids: Mapped[list] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class DocumentIndex(Base):
    __tablename__ = "document_indexes"
    __table_args__ = (ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),)
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    generation_id: Mapped[UUID] = mapped_column(ForeignKey("app.index_generations.id", ondelete="RESTRICT"), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("app.document_versions.id", ondelete="RESTRICT"))


class Chunk(Record, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        UniqueConstraint("document_version_id", "generation_id", "start_offset", name="uq_chunks_span_generation"),
        CheckConstraint("start_offset>=0 AND end_offset>start_offset AND char_length(content)=end_offset-start_offset", name="exact_span"),
        CheckConstraint("line_start>=1 AND line_end>=line_start AND token_count>=0", name="valid_locator"),
        CheckConstraint("public.vector_norm(embedding) BETWEEN 0.9999 AND 1.0001", name="unit_embedding"),
        Index("ix_chunks_scope", "workspace_id", "project_id", "collection_id", "generation_id", "document_version_id"),
        Index("ix_chunks_search", "search", postgresql_using="gin"),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64}),
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("app.document_versions.id", ondelete="RESTRICT"))
    generation_id: Mapped[UUID] = mapped_column(ForeignKey("app.index_generations.id", ondelete="RESTRICT"))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    terms: Mapped[dict] = mapped_column(JSONB)
    token_count: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict] = mapped_column(JSONB)
    search: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english'::regconfig,content)", persisted=True))
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768))
