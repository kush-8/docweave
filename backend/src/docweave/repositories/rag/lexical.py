"""Lexical SQL against the caller's authorized transaction."""

from sqlalchemy import text
from docweave.repositories.rag.scope import SCOPE


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

async def search(session, parameters, strategy, *, explain=False):
    statement = NATIVE if strategy == "native" else BM25
    if explain:
        return await session.scalar(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + statement), parameters)
    return (await session.execute(text(statement), parameters)).mappings().all()
