"""Shared authorized corpus for native full-text, SQL BM25, exact and HNSW experiments."""

import hashlib
import json
import math
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from docweave.db import tenant_session


class RetrievalError(Exception):
    pass


INDEX_ERRORS = {"P0002": "not_found", "42501": "forbidden", "DW020": "awaiting_approval", "DW021": "snapshot_unavailable", "DW022": "generation_unavailable"}


def vector_literal(vector):
    if not isinstance(vector, list) or len(vector) != 768:
        raise RetrievalError("invalid_vector")
    if any(type(value) not in (float, int) or abs(value) > 1.0001 or not math.isfinite(value) for value in vector):
        raise RetrievalError("invalid_vector")
    if not math.isclose(sum(value * value for value in vector), 1, rel_tol=0.0001):
        raise RetrievalError("invalid_vector")
    return json.dumps(vector)


async def index_input(actor, document_id, generation_id, engine):
    try:
        async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            return await session.scalar(text("SELECT app.index_input(:document,:generation)"), {"document": document_id, "generation": generation_id})
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
        for start in range(0, len(spans), 64):
            current = await index_input(actor, document_id, generation_id, worker_engine)
            if current["version_id"] != snapshot["version_id"]:
                raise RetrievalError("snapshot_unavailable")
            batch = spans[start:start + 64]
            bodies = [parsed["text"][span["start"]:span["end"]] for span in batch]
            vectors = await embedder(bodies)
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                raise RetrievalError("invalid_vector")
            rows.extend({**span, "content": body, "embedding": vector_literal(vector)} for span, body, vector in zip(batch, bodies, vectors))
    publication_started = time.perf_counter()
    try:
        async with tenant_session(worker_engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
            for start in range(0, len(rows), 64):
                await session.execute(text("SELECT app.insert_chunks(:document,:generation,:version,CAST(:chunks AS jsonb))"),
                    {"document": document_id, "generation": generation_id, "version": UUID(snapshot["version_id"]),
                        "chunks": json.dumps(rows[start:start + 64])})
            await session.execute(text("SELECT app.activate_index(:document,:generation,:version,:expected)"),
                {"document": document_id, "generation": generation_id, "version": UUID(snapshot["version_id"]), "expected": len(spans)})
    except DBAPIError as error:
        code = INDEX_ERRORS.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise RetrievalError(code) from None
        raise
    return {"chunks": len(spans), "created": bool(rows), "publish_ms": (time.perf_counter()-publication_started)*1000}


SCOPE = "project_id=:project AND collection_id=ANY(CAST(:collections AS uuid[])) AND generation_id=:generation"
NATIVE = f"""SELECT *,ts_rank_cd(search,websearch_to_tsquery('english',:query))::double precision AS score
    FROM app.chunks WHERE {SCOPE} AND search @@ websearch_to_tsquery('english',:query) ORDER BY score DESC,id LIMIT 30"""
BM25 = f"""WITH eligible AS MATERIALIZED (SELECT * FROM app.chunks WHERE {SCOPE}),
    corpus AS (SELECT count(*)::double precision AS n,avg(token_count)::double precision AS average_length FROM eligible),
    words AS (SELECT term FROM jsonb_object_keys(app.bm25_terms(:query)) AS query_words(term)),
    frequencies AS (SELECT w.term,count(e.id) FILTER (WHERE e.terms ? w.term)::double precision AS df
        FROM words w CROSS JOIN eligible e GROUP BY w.term)
    SELECT e.*,rank.score FROM eligible e CROSS JOIN LATERAL (
        SELECT sum(ln(1+(c.n-f.df+0.5)/(f.df+0.5)) * ((e.terms->>f.term)::double precision*2.2) /
            ((e.terms->>f.term)::double precision+1.2*(0.25+0.75*e.token_count/nullif(c.average_length,0)))) AS score
        FROM frequencies f CROSS JOIN corpus c WHERE e.terms ? f.term) rank
    WHERE rank.score>0 ORDER BY rank.score DESC,e.id LIMIT 30"""
EXACT = f"""WITH eligible AS MATERIALIZED (SELECT * FROM app.chunks WHERE {SCOPE})
    SELECT *,1-(embedding <=> CAST(:vector AS public.vector)) AS score FROM eligible
    ORDER BY embedding <=> CAST(:vector AS public.vector),id LIMIT 30"""
HNSW = f"""SELECT * FROM (SELECT *,1-(embedding <=> CAST(:vector AS public.vector)) AS score FROM app.chunks WHERE {SCOPE}
    ORDER BY embedding <=> CAST(:vector AS public.vector) LIMIT 30) candidates ORDER BY score DESC,id"""
HNSW_SETTINGS = {"hnsw.iterative_scan": "strict_order", "hnsw.ef_search": "100", "hnsw.max_scan_tuples": "20000",
    "enable_seqscan": "off", "enable_sort": "off"}


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
        await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(generation_id)})
        if await session.scalar(text("SELECT id FROM app.projects WHERE id=:id"), {"id": project_id}) is None:
            raise RetrievalError("not_found")
        if not scopes:
            return result
        found = (await session.execute(text("SELECT id FROM app.collections WHERE project_id=:project AND id=ANY(CAST(:ids AS uuid[]))"),
            {"project": project_id, "ids": scopes})).scalars().all()
        if set(found) != set(scopes):
            raise RetrievalError("not_found")
        if await session.scalar(text("SELECT id FROM app.index_generations WHERE id=:id AND enabled"), {"id": generation_id}) is None:
            raise RetrievalError("generation_unavailable")
        for collection in scopes:
            if not await session.scalar(text("SELECT app.index_policy(:collection,:generation,'read')"), {"collection": collection, "generation": generation_id}):
                raise RetrievalError("awaiting_approval")
        parameters = {"project": project_id, "collections": scopes, "generation": generation_id, "query": query, "vector": encoded_vector}
        await session.execute(text("SET LOCAL statement_timeout='5s'"))
        await session.execute(text("SET LOCAL jit=off"))
        count, versions = (await session.execute(text(f"SELECT count(*),array_agg(DISTINCT document_version_id) FROM app.chunks WHERE {SCOPE}"), parameters)).one()
        result["eligible_count"], result["snapshot_ids"] = count, sorted(str(identity) for identity in (versions or []))
        for name, statement in (("lexical", NATIVE if lexical == "native" else BM25), ("vector", EXACT if vector == "exact" else HNSW)):
            if name == "vector" and vector == "hnsw":
                for setting, value in HNSW_SETTINGS.items():
                    await session.execute(text("SELECT set_config(:setting,:value,true)"), {"setting": setting, "value": value})
            started = time.perf_counter()
            rows = (await session.execute(text(statement), parameters)).mappings().all()
            result[name] = [evidence(row) for row in rows]
            result["latency_ms"][name] = (time.perf_counter() - started) * 1000
            if explain:
                result["plans"][name] = await session.scalar(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + statement), parameters)
        captured = {hit["chunk_id"] for channel in ("lexical", "vector") for hit in result[channel]}
        if captured:
            current = set((await session.execute(text("SELECT id FROM app.chunks WHERE id=ANY(CAST(:ids AS uuid[]))"), {"ids": list(captured)})).scalars())
            if current != captured:
                raise RetrievalError("scope_changed")
            if any(str(hit["document_version_id"]) not in result["snapshot_ids"] for channel in ("lexical", "vector") for hit in result[channel]):
                raise RetrievalError("scope_changed")
    return result
