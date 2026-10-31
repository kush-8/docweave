"""Validate requests and coordinate authorized lexical and vector channels."""

import time
from docweave.db.sessions import tenant_session
from docweave.rag.contracts import RetrievalError
from docweave.repositories.rag import lexical as lexical_repository, vector as vector_repository, scope
from docweave.repositories.rag.vector import HNSW_SETTINGS, vector_literal


def evidence(row):
    return {"chunk_id": row["id"], "document_id": row["document_id"], "document_version_id": row["document_version_id"],
        "generation_id": row["generation_id"], "collection_id": row["collection_id"], "quote": row["content"],
        "source_url": row["source_url"], "captured_at": row["captured_at"], "provenance": row["provenance"], "score": float(row["score"]),
        "locator": {"start": row["start_offset"], "end": row["end_offset"], "heading": row["heading"], "line_start": row["line_start"], "line_end": row["line_end"]}}

async def retrieve_channels(actor, project_id, query, *, collection_ids, generation_id, query_vector, engine, lexical="native", vector="exact", explain=False):
    if lexical not in ("native", "bm25") or vector not in ("exact", "hnsw"):
        raise RetrievalError("invalid_strategy")
    if not isinstance(query, str) or not query.strip() or len(query) > 4096 or "\x00" in query:
        raise RetrievalError("invalid_query")
    encoded_vector = vector_literal(query_vector)
    if not isinstance(collection_ids, list) or len(collection_ids) > 100:
        raise RetrievalError("invalid_scope")
    scopes = list(dict.fromkeys(collection_ids))
    result = {"lexical": [], "vector": [], "plans": {}, "latency_ms": {}, "settings": HNSW_SETTINGS if vector == "hnsw" else {},
        "eligible_count": 0, "snapshot_ids": []}
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        if not await scope.authorize(session, project_id, scopes, generation_id):
            return result
        parameters = {"project": project_id, "collections": scopes, "generation": generation_id, "query": query, "vector": encoded_vector}
        result["eligible_count"], result["snapshot_ids"] = await scope.inspect_snapshot(session, parameters)
        for name, repository, strategy in (("lexical", lexical_repository, lexical), ("vector", vector_repository, vector)):
            if name == "vector":
                await vector_repository.configure(session, strategy)
            started = time.perf_counter()
            rows = await repository.search(session, parameters, strategy)
            result[name] = [evidence(row) for row in rows]
            result["latency_ms"][name] = (time.perf_counter() - started) * 1000
            if explain:
                result["plans"][name] = await repository.search(session, parameters, strategy, explain=True)
        await scope.recheck(session, result)
    return result
