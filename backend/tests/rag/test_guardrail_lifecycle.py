"""Guarded disposable PostgreSQL; scans never fetch or embed documents."""
from dataclasses import asdict
import json
from uuid import UUID
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.database.test_database import databases, test_urls, A, PA
from tests.personal.test_personal_retrieval import seed
from docweave.core.guardrails import RULE_REVISION, assess_text
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.storage.artifacts import ArtifactStore

pytestmark=pytest.mark.anyio


async def activate(owner, revision):
    async with owner.begin() as c:
        epoch=await c.scalar(text('SELECT epoch FROM app.guardrail_policy'))
        return await c.scalar(text('SELECT app.activate_guardrail_policy(:revision,:epoch)'),{'revision':revision,'epoch':epoch})


async def eligible(owner, version):
    async with owner.connect() as c:
        return await c.scalar(text('SELECT app.personal_assessment_eligible(:version)'),{'version':version})


async def test_rules_hold_citations_and_rescan_retained_vectors_without_embedding(databases,tmp_path):
    from docweave.repositories import guardrails as repository
    from docweave.services.guardrails import run_rescan, reconcile_rescans
    owner,_=databases
    generation,revision,collection,version,chunk,vector=await seed(owner)
    assert await eligible(owner,version)
    store=ArtifactStore(tmp_path)
    store.put(version,json.dumps({'text':'React state uses hooks.','configuration':'fixture:text/plain'}).encode())
    async with owner.connect() as c:
        document=await c.scalar(text('SELECT document_id FROM app.document_versions WHERE id=:id'),{'id':version})
        citation={'chunk_id':str(chunk),'document_version_id':str(version),'generation_id':str(generation),'excerpt':'React state uses hooks.'}
        await c.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(A)})
        assert await c.scalar(text('SELECT app.personal_citations_current(:project,CAST(:citations AS jsonb))'),{'project':PA,'citations':json.dumps([citation])})
    await activate(owner,'retired-rules')
    assert not await eligible(owner,version)
    await activate(owner,RULE_REVISION)
    assert not await eligible(owner,version)
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        assert await reconcile_rescans(worker)==1
        assert await reconcile_rescans(worker)==0
        async with owner.connect() as c:
            job=await c.scalar(text('SELECT id FROM app.guardrail_rescans WHERE document_version_id=:id ORDER BY epoch DESC LIMIT 1'),{'id':version})
        await run_rescan(job,engine=worker,store=store)
        assert await eligible(owner,version)
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT count(*) FROM app.chunks WHERE document_version_id=:id'),{'id':version})==1
            assert await c.scalar(text('SELECT count(*) FROM app.cost_reservations'))==0
            assert await c.scalar(text('SELECT status FROM app.documents WHERE id=:id'),{'id':document})=='ready'
    finally:
        await worker.dispose()


async def test_missing_artifact_fails_closed_and_operator_retry_recovers(databases,tmp_path):
    from docweave.services.guardrails import run_rescan, reconcile_rescans
    from docweave.repositories import guardrails as repository
    owner,_=databases
    _,_,_,version,_,_=await seed(owner)
    await activate(owner,'retired-rules')
    await activate(owner,RULE_REVISION)
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    store=ArtifactStore(tmp_path)
    try:
        await reconcile_rescans(worker)
        async with owner.connect() as c:
            job=await c.scalar(text('SELECT id FROM app.guardrail_rescans WHERE document_version_id=:id'),{'id':version})
        await run_rescan(job,engine=worker,store=store)
        assert not await eligible(owner,version)
        async with owner.begin() as c:
            assert await c.scalar(text('SELECT status FROM app.guardrail_rescans WHERE id=:id'),{'id':job})=='failed'
            assert await repository.retry(c,version)
        store.put(version,json.dumps({'text':'React state uses hooks.','configuration':'fixture:text/plain'}).encode())
        await run_rescan(job,engine=worker,store=store)
        assert await eligible(owner,version)
    finally:
        await worker.dispose()
