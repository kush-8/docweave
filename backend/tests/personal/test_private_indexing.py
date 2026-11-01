"""Private index continuation runs against guarded disposable PostgreSQL and fake transports."""
import asyncio
import json
from decimal import Decimal
from uuid import UUID,uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.support.personal import collections
from tests.github.test_github import github_login
from tests.database.test_database import databases,test_urls
from tests.providers.test_budget import profile
from docweave.core.identity import Actor
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.rag.contracts import CONFIGURATION
from docweave.rag.parsing import parse_text
from docweave.services.ingestion import run_ingestion
from docweave.services.source_review import seal_candidate
from docweave.services.private_indexing import enqueue_document_index,reconcile_private_indexes,run_private_index_job
from docweave.repositories import private_indexing as repository
from docweave.storage.artifacts import ArtifactStore

pytestmark=pytest.mark.anyio

@pytest.fixture
async def private_index(collections,tmp_path):
    c=collections
    dependency={'id':'dep','technology':'example','ecosystem':'python','docs_target':'1.2.3'}
    async with c['owner'].begin() as connection:
        await connection.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:id'),{'id':UUID(c['project']),'stack':json.dumps([dependency])})
    app=c['data']['app']
    settings,_,client=app.state.github
    project=(await c['admin'].get('/api/v1/projects/'+c['project'])).json()
    candidate={'source_url':'https://docs.example.org/v1/guide.md','origin':'https://docs.example.org','path_prefix':'/v1/','attribution':'Publisher'}
    token=seal_candidate(settings.encryption_key,c['user']['id'],project,dependency,candidate)
    accepted=await c['admin'].post(f"/api/v1/projects/{c['project']}/documentation/dep/review-source",json={'expected_revision':1,'candidate_token':token,'coverage':{'granularity':'exact','version':'1.2.3'}},headers=c['headers'])
    assert accepted.status_code==202,accepted.text
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    store=ArtifactStore(tmp_path)
    async def fetcher(selection):
        return b'# Example\nUse the method.','text/markdown'
    try:
        await run_ingestion(UUID(accepted.json()['job_id']),engine=worker,store=store,parser=parse_text,fetcher=fetcher)
        identity=await profile(c['owner'],role='embedding',fixed=Decimal('0.01'))
        async with c['owner'].begin() as connection:
            old=identity
            identity=uuid4()
            await connection.execute(text("INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,max_attempts,enabled,capabilities_verified,account_verified,pricing_verified) SELECT :id,provider,'gemini-embedding-2',backend,role,processor_ids,input_usd_per_million,output_usd_per_million,fixed_usd,16384,max_output_tokens,max_attempts,enabled,capabilities_verified,account_verified,pricing_verified FROM app.provider_profiles WHERE id=:old"),{'id':identity,'old':old})
            generation=await connection.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES('gemini-embedding-2','fake-google',768,'unit-l2',:config,'[\"test:budget:google\"]',true) RETURNING id"),{'config':CONFIGURATION})
            for table,column,value in [('project_processor_approvals','project_id',c['project']),('collection_processor_approvals','collection_id',c['collection'])]:
                await connection.execute(text(f"INSERT INTO app.{table}({column},processor_id,approved_by) VALUES(:id,'test:budget:google',:actor)"),{'id':UUID(value),'actor':UUID(c['user']['id'])})
            document=await connection.scalar(text('SELECT document_id FROM app.ingestion_jobs WHERE id=:id'),{'id':UUID(accepted.json()['job_id'])})
        actor=Actor(UUID(c['user']['id']))
        job=await enqueue_document_index(actor,document,generation,worker)
        assert job is not None
        yield {**c,'worker':worker,'store':store,'settings':settings,'client':client,'actor':actor,'document':document,'generation':generation,'profile':identity,'job':job,
            'config':{'RAG_GENERATION_ID':str(generation),'EMBEDDING_PROFILE_ID':str(identity),'GEMINI_API_KEY':'fixture'}}
    finally:
        await worker.dispose()

async def run(c):
    await run_private_index_job(c['job'],engine=c['worker'],store=c['store'],settings=c['settings'],client=c['client'],config=c['config'])

async def state(c):
    async with c['owner'].connect() as connection:
        return await connection.scalar(text('SELECT status FROM app.private_index_jobs WHERE id=:id'),{'id':c['job']})

async def test_private_index_is_deduplicated_queued_and_published(private_index,monkeypatch):
    c=private_index
    assert await enqueue_document_index(c['actor'],c['document'],c['generation'],c['worker'])==c['job']
    assert await reconcile_private_indexes(c['worker'],c['generation'])==1
    assert await reconcile_private_indexes(c['worker'],c['generation'])==0
    calls=[]
    async def provider(*args,**kwargs):
        calls.append(args)
        return {'embedding':{'values':[1.0]+[0.0]*767},'usageMetadata':{'promptTokenCount':1}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    await run(c)
    assert await state(c)=='completed'
    assert len(calls)==1
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes'))==1
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations'))==1
        assert await connection.scalar(text('SELECT response IS NOT NULL FROM app.personal_provider_calls'))
        assert not await connection.scalar(text("SELECT has_table_privilege('docweave_runtime','app.private_index_jobs','INSERT')"))
    await run(c)
    assert len(calls)==1

async def test_private_index_uncertain_response_is_never_replayed(private_index,monkeypatch):
    c=private_index
    calls=[]
    async def provider(*args,**kwargs):
        calls.append(args)
        raise TimeoutError
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    await run(c)
    assert await state(c)=='completion_unknown'
    assert await reconcile_private_indexes(c['worker'],c['generation'])==0
    await run(c)
    assert len(calls)==1
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations'))==1
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes'))==0

async def test_private_index_recovery_reuses_recorded_response_and_original_charge(private_index,monkeypatch):
    c=private_index
    calls=[]
    async def provider(*args,**kwargs):
        calls.append(args)
        return {'embedding':{'values':[1.0]+[0.0]*767},'usageMetadata':{'promptTokenCount':1}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    from docweave.services import private_indexing
    original=private_indexing.index_document
    async def interrupted(*args,**kwargs):
        async def stop():
            raise asyncio.CancelledError
        await original(*args,**{**kwargs,'authorize':stop})
    monkeypatch.setattr(private_indexing,'index_document',interrupted)
    with pytest.raises(asyncio.CancelledError):
        await run(c)
    assert await state(c)=='running'
    async with c['owner'].begin() as connection:
        assert await connection.scalar(text('SELECT response IS NOT NULL FROM app.personal_provider_calls'))
        await connection.execute(text("UPDATE app.private_index_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=:id"),{'id':c['job']})
    monkeypatch.setattr(private_indexing,'index_document',original)
    await run(c)
    assert await state(c)=='completed'
    assert len(calls)==1
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations'))==1
        assert await connection.scalar(text('SELECT sum(charged_usd) FROM app.cost_reservations'))==Decimal('0.01')

@pytest.mark.parametrize('revocation',['session','identity','repository','source','consent','profile','generation','assessment','budget','owner','stack'])
async def test_private_index_fresh_authority_blocks_calls_and_publication(private_index,monkeypatch,revocation):
    c=private_index
    calls=[]
    async def provider(*args,**kwargs):
        calls.append(args)
        return {'embedding':{'values':[1.0]+[0.0]*767}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    async with c['owner'].begin() as connection:
        statements={
            'session':"UPDATE app.auth_sessions SET expires_at=now()-interval '1 second'",
            'source':'UPDATE app.documentation_selections SET active=false',
            'owner':"UPDATE app.projects SET owner_user_id=NULL WHERE id=:project",
            'stack':"UPDATE app.projects SET stack='[]'::jsonb WHERE id=:project",
            'consent':'DELETE FROM app.collection_processor_approvals',
            'profile':'UPDATE app.provider_profiles SET enabled=false',
            'generation':'UPDATE app.index_generations SET enabled=false',
            'assessment':'UPDATE app.document_assessments SET credential_blocked=true',
            'budget':"INSERT INTO app.cost_reservations(actor_id,project_id,profile_id,operation_hash,month,input_tokens,output_tokens,maximum_usd,status) VALUES(:actor,:project,:profile,repeat('a',64),app.budget_month(now()),1,0,21,'uncertain')",
        }
        if revocation in statements:
            await connection.execute(text(statements[revocation]),{'actor':c['actor'].user_id,'project':UUID(c['project']),'profile':c['profile']})
    if revocation=='identity':
        async def identity(*args): return {'id':999}
        c['client'].user=identity
    if revocation=='repository':
        async def denied(*args): raise ValueError('denied')
        c['client'].repository=denied
    await run(c)
    assert not calls
    assert await state(c)!='completed'
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes'))==0

async def test_source_revoked_during_hosted_call_cannot_checkpoint_publish_or_replay(private_index,monkeypatch):
    c=private_index
    calls=[]
    async def provider(*args,**kwargs):
        calls.append(args)
        async with c['owner'].begin() as connection:
            await connection.execute(text('UPDATE app.documentation_selections SET active=false'))
        return {'embedding':{'values':[1.0]+[0.0]*767},'usageMetadata':{'promptTokenCount':1}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    await run(c)
    assert await state(c)=='capacity'
    async with c['owner'].begin() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes'))==0
        assert await connection.scalar(text('SELECT response IS NULL FROM app.personal_provider_calls'))
        await connection.execute(text('UPDATE app.documentation_selections SET active=true'))
    await run(c)
    assert await state(c)=='completion_unknown'
    assert len(calls)==1

async def test_publication_refresh_blocks_revoked_source_after_valid_recorded_response(private_index,monkeypatch):
    c=private_index
    async def provider(*args,**kwargs):
        return {'embedding':{'values':[1.0]+[0.0]*767}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    from docweave.services import private_indexing
    original=private_indexing.index_document
    async def revoke_before_publication(*args,**kwargs):
        authorize=kwargs['authorize']
        async def revoked():
            async with c['owner'].begin() as connection:
                await connection.execute(text('UPDATE app.documentation_selections SET active=false'))
            await authorize()
        await original(*args,**{**kwargs,'authorize':revoked})
    monkeypatch.setattr(private_indexing,'index_document',revoke_before_publication)
    await run(c)
    assert await state(c)=='capacity'
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT response IS NOT NULL FROM app.personal_provider_calls'))
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes'))==0

async def test_checkpoint_requires_matching_live_private_intent_and_runtime_cannot_claim(private_index,monkeypatch):
    c=private_index
    from docweave.services import private_indexing
    original=private_indexing.index_document
    async def provider(*args,**kwargs):
        return {'embedding':{'values':[1.0]+[0.0]*767}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',provider)
    async def interrupt(*args,**kwargs):
        async def stop(): raise asyncio.CancelledError
        await original(*args,**{**kwargs,'authorize':stop})
    monkeypatch.setattr(private_indexing,'index_document',interrupt)
    with pytest.raises(asyncio.CancelledError): await run(c)
    from docweave.repositories.personal_providers import checkpoint
    async with c['owner'].begin() as connection:
        reservation=await connection.scalar(text('SELECT id FROM app.cost_reservations'))
        response=await connection.scalar(text('SELECT response FROM app.personal_provider_calls'))
        await connection.execute(text("UPDATE app.private_index_jobs SET key_hash=repeat('0',64)"))
    with pytest.raises(DBAPIError):
        async with c['worker'].begin() as connection:
            await checkpoint(connection,reservation,response)
    with pytest.raises(DBAPIError):
        async with c['runtime'].begin() as connection:
            await repository.claim(connection,c['job'])

async def test_private_index_migration_roundtrip_and_security(databases,test_urls):
    from tests.database.test_database import migrate
    await migrate(test_urls[1],'0035_source_media',downgrade=True)
    await migrate(test_urls[1],'head')
    owner,_=databases
    async with owner.connect() as connection:
        assert not await connection.scalar(text("SELECT has_function_privilege('docweave_runtime','app.private_index_context(uuid,uuid,uuid,text)','EXECUTE')"))
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_worker','app.private_index_context(uuid,uuid,uuid,text)','EXECUTE')"))

async def test_reconcile_discovers_prepared_artifact_when_generation_becomes_available(private_index):
    c=private_index
    async with c['owner'].begin() as connection:
        await connection.execute(text('DELETE FROM app.private_index_jobs'))
        status=await connection.scalar(text('SELECT status FROM app.documents WHERE id=:id'),{'id':c['document']})
        assert status=='awaiting_approval'  # Publication precedes the persisted guard assessment.
    assert await reconcile_private_indexes(c['worker'],None)==0
    assert await reconcile_private_indexes(c['worker'],c['generation'])==1
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.private_index_jobs'))==1
        assert await connection.scalar(text("SELECT count(*) FROM queue.procrastinate_jobs WHERE task_name='docweave.private_index' AND status='todo'"))==1
