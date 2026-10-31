"""Vector SQL serialization and search in a caller-owned transaction."""

import json
from sqlalchemy import text
from docweave.rag.contracts import validate_vector
from docweave.repositories.rag.scope import SCOPE


EXACT = f"""WITH eligible AS MATERIALIZED (SELECT * FROM app.chunks WHERE {SCOPE})
    SELECT *,1-(embedding <=> CAST(:vector AS public.vector)) AS score FROM eligible
    ORDER BY embedding <=> CAST(:vector AS public.vector),id LIMIT 30"""
HNSW = f"""SELECT * FROM (SELECT *,1-(embedding <=> CAST(:vector AS public.vector)) AS score FROM app.chunks WHERE {SCOPE}
    ORDER BY embedding <=> CAST(:vector AS public.vector) LIMIT 30) candidates ORDER BY score DESC,id"""
HNSW_SETTINGS = {"hnsw.iterative_scan": "strict_order", "hnsw.ef_search": "100", "hnsw.max_scan_tuples": "20000",
    "enable_seqscan": "off", "enable_sort": "off"}


def vector_literal(vector):
    validate_vector(vector)
    return json.dumps(vector)

async def search(session, parameters, strategy, *, explain=False):
    statement = EXACT if strategy == "exact" else HNSW
    if explain:
        return await session.scalar(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + statement), parameters)
    return (await session.execute(text(statement), parameters)).mappings().all()

async def configure(session, strategy):
    if strategy == "hnsw":
        for setting, value in HNSW_SETTINGS.items():
            await session.execute(text("SELECT set_config(:setting,:value,true)"), {"setting": setting, "value": value})
