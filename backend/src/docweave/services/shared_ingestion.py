"""Fetch, scan and atomically index one immutable approved public source."""
from dataclasses import asdict
import hashlib
import inspect
import json
from uuid import UUID,uuid4
from docweave.integrations.public_sources import fetch_document
from docweave.integrations.parser import container_parse
from docweave.core.guardrails import assess_text
from docweave.rag.embeddings import embed_spans
from docweave.repositories import catalog as repository

async def run_catalog_job(job_id,*,engine,store,parser=container_parse,fetcher=fetch_document,embedder=None,embedder_factory=None):
    async with engine.begin() as c:
        job=await repository.claim(c,job_id)
    if not job:
        return
    token=UUID(job['lease_token'])
    if embedder_factory is not None:
        embedder=embedder_factory(job,token)
    async def authorized():
        async with engine.begin() as c:
            if not await repository.authorized(c,job_id,token):
                raise ValueError('Source authority changed')
    async def snapshot():
        async with engine.begin() as c:
            return await repository.index_input(c,job_id,token)
    status='failed'
    try:
        async with engine.begin() as c:
            current=await repository.snapshot(c,job_id,token)
        if current:
            parsed=json.loads(store.read(current['version_id']))
            if not current['eligible']:
                status='pending_review'
                return
        else:
            content,media=await fetcher(job['source'],authorize=authorized)
            await authorized()
            parsed=parser(content,media)
            if inspect.isawaitable(parsed):
                parsed=await parsed
            version=uuid4()
            assessment=assess_text(parsed['text'],document_version=str(version),parser_config={'configuration':parsed['configuration']})
            store.put(version,json.dumps(parsed,ensure_ascii=False).encode())
            # An uncertain acknowledgement must never erase a potentially referenced artifact.
            async with engine.begin() as c:
                if not await repository.publish_snapshot(c,job_id,token,version,parsed,asdict(assessment)):
                    return
            if assessment.credential_blocked or assessment.injection_flagged or not assessment.complete:
                status='pending_review'
                return
        if hashlib.sha256(parsed['text'].encode()).hexdigest()!=parsed['sha256']:
            raise ValueError('Snapshot mismatch')
        current=await snapshot()
        if current['existing_chunks']==len(parsed['chunks']):
            rows=[]
        elif embedder is None:
            status='capacity'
            return
        else:
            rows=await embed_spans(parsed,current,embedder,snapshot)
        await authorized()
        async with engine.begin() as c:
            await repository.publish_index(c,job_id,token,rows,len(parsed['chunks']))
        status='completed'
    finally:
        async with engine.begin() as c:
            await repository.finish(c,job_id,token,status)
            await repository.wake_waits(c)
