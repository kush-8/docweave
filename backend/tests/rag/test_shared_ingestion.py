"""Shared jobs are deduplicated and become searchable only after publication."""
from uuid import UUID
import pytest
from sqlalchemy import text
from tests.database.test_database import A,B,PA,PB,databases,test_urls
from tests.personal.test_personal_retrieval import seed
from docweave.db.engine import make_engine
from docweave.core.settings import database_url

pytestmark=pytest.mark.anyio

async def test_shared_reconciliation_queues_only_one_global_job(databases):
    owner,_=databases
    generation,revision,collection,version,chunk,vector=await seed(owner)
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        for project,actor in ((PA,A),(PB,B)):
            async with worker.begin() as c:
                await c.execute(text("SELECT app.personal_reconcile_catalog(:p,:a,CAST(:choices AS jsonb),:g)"),{'p':project,'a':actor,'choices':'[{"dependency_id":"react","revision_id":"'+str(revision)+'"}]','g':generation})
        async with owner.begin() as c:
            assert await c.scalar(text('SELECT count(*) FROM app.catalog_jobs WHERE catalog_revision_id=:r'),{'r':revision})==0
            replacement=await c.scalar(text('INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) SELECT model,backend,dimensions,normalization,chunker,processor_ids,enabled FROM app.index_generations WHERE id=:g RETURNING id'),{'g':generation})
        for project,actor in ((PA,A),(PB,B)):
            async with worker.begin() as c:
                await c.execute(text("SELECT app.personal_reconcile_catalog(:p,:a,CAST(:choices AS jsonb),:g)"),{'p':project,'a':actor,'choices':'[{"dependency_id":"react","revision_id":"'+str(revision)+'"}]','g':replacement})
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT count(*) FROM app.catalog_jobs WHERE catalog_revision_id=:r'),{'r':revision})==1
            assert await c.scalar(text("SELECT count(*) FROM queue.procrastinate_jobs WHERE task_name='docweave.catalog'"))==1
    finally:
        await worker.dispose()


async def test_public_source_is_scanned_and_indexed_before_ready(databases,tmp_path):
    from tests.database.test_public_catalog_schema import add_revision
    from docweave.services.shared_ingestion import run_catalog_job
    from docweave.storage.artifacts import ArtifactStore
    from docweave.rag.parsing import parse_text
    from docweave.rag.contracts import CONFIGURATION
    owner,_=databases
    async with owner.begin() as c:
        await c.execute(text('UPDATE app.projects SET owner_user_id=:a,stack=CAST(:s AS jsonb) WHERE id=:p'),{'a':A,'p':PA,'s':'[{"id":"react","technology":"react","docs_target":"19.1.0","role":"runtime","direct":true}]'})
        revision=await add_revision(c,enabled=True,approved=True)
        generation=await c.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES ('fixture','fixture',768,'unit-l2',:config,'[\"fixture\"]',true) RETURNING id"),{'config':CONFIGURATION})
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    store=ArtifactStore(tmp_path)
    async def fetcher(selection,*,authorize):
        await authorize()
        return b'React state uses hooks.','text/plain'
    async def embedder(bodies):
        return [[1.0]+[0.0]*767 for _ in bodies]
    try:
        async with worker.begin() as c:
            await c.execute(text('SELECT app.personal_reconcile_catalog(:p,:a,CAST(:choices AS jsonb),:g)'),{'p':PA,'a':A,'choices':'[{"dependency_id":"react","revision_id":"'+str(revision)+'"}]','g':generation})
        async with owner.connect() as c:
            job=await c.scalar(text('SELECT id FROM app.catalog_jobs WHERE catalog_revision_id=:r'),{'r':revision})
        await run_catalog_job(job,engine=worker,store=store,parser=parse_text,fetcher=fetcher,embedder=embedder)
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT status FROM app.catalog_jobs WHERE id=:id'),{'id':job})=='completed'
            assert await c.scalar(text('SELECT count(*) FROM app.document_indexes WHERE generation_id=:g'),{'g':generation})==1
            assert await c.scalar(text('SELECT count(*) FROM app.document_assessments WHERE complete AND NOT credential_blocked'))==1
    finally:
        await worker.dispose()
