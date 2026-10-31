"""Snapshot and publication SQL; the caller owns transaction boundaries."""

import json
from uuid import UUID
from sqlalchemy import text
from docweave.repositories.rag.vector import vector_literal


INDEX_ERRORS = {"P0002": "not_found", "42501": "forbidden", "DW020": "awaiting_approval", "DW021": "snapshot_unavailable", "DW022": "generation_unavailable"}


async def index_input(session, document_id, generation_id):
    return await session.scalar(text("SELECT app.index_input(:document,:generation)"), {"document": document_id, "generation": generation_id})

async def publish(session, document_id, generation_id, snapshot, rows, expected):
    for start in range(0, len(rows), 64):
        await session.execute(text("SELECT app.insert_chunks(:document,:generation,:version,CAST(:chunks AS jsonb))"),
            {"document": document_id, "generation": generation_id, "version": UUID(snapshot["version_id"]),
                "chunks": json.dumps([{**row, "embedding": vector_literal(row["embedding"])} for row in rows[start:start + 64]])})
    await session.execute(text("SELECT app.activate_index(:document,:generation,:version,:expected)"),
        {"document": document_id, "generation": generation_id, "version": UUID(snapshot["version_id"]), "expected": expected})
