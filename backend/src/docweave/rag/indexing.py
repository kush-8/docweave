"""Verify immutable artifacts, coordinate embeddings, then publish atomically."""

import hashlib, json, time
from sqlalchemy.exc import DBAPIError
from docweave.db.sessions import tenant_session
from docweave.rag.contracts import RetrievalError
from docweave.rag.embeddings import embed_spans
from docweave.repositories.rag import indexing as repository
from docweave.repositories.rag.indexing import INDEX_ERRORS


async def index_input(actor, document_id, generation_id, engine):
    try:
        async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            return await repository.index_input(session, document_id, generation_id)
    except DBAPIError as error:
        code = INDEX_ERRORS.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise RetrievalError(code) from None
        raise

async def index_document(actor, document_id, generation_id, *, worker_engine, store, embedder=None):
    # Hosted adapters/admission are added in 3C; there is no automatic local transport.
    snapshot = await index_input(actor, document_id, generation_id, worker_engine)
    parsed = json.loads(store.read(snapshot["version_id"]))
    if hashlib.sha256(parsed["text"].encode()).hexdigest() != snapshot["content_hash"] or parsed["configuration"] != snapshot["configuration"]:
        raise RetrievalError("snapshot_unavailable")
    spans = parsed["chunks"]
    rows = []
    if snapshot["existing_chunks"] != len(spans):
        if embedder is None:
            raise RetrievalError("waiting_capacity")
        rows = await embed_spans(parsed, snapshot, embedder, lambda: index_input(actor, document_id, generation_id, worker_engine))
    publication_started = time.perf_counter()
    try:
        async with tenant_session(worker_engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            await repository.publish(session, document_id, generation_id, snapshot, rows, len(spans))
    except DBAPIError as error:
        code = INDEX_ERRORS.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise RetrievalError(code) from None
        raise
    return {"chunks": len(spans), "created": bool(rows), "publish_ms": (time.perf_counter()-publication_started)*1000}
