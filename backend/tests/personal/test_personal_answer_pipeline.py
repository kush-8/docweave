"""Actual SQL/search/accounting with mocked provider HTTP; no paid calls."""
import json
from uuid import UUID,uuid4
import pytest
from sqlalchemy import text
from tests.github.test_github import github_login
from tests.database.test_database import A,PA,databases,test_urls
from tests.personal.test_personal_retrieval import seed
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.services.github_auth import session_context
from docweave.services.personal_worker import run_personal_job
from docweave.services.answer_engine import AnswerEngine

pytestmark=pytest.mark.anyio

async def test_personal_question_runs_hybrid_rerank_and_validated_answer(github_login,monkeypatch):
    settings,runtime,owner,github,state,cookie,_,_=github_login
    user,_=await session_context(settings,runtime,github,cookie)
    actor=UUID(user['id'])
    generation,revision,collection,version,chunk,vector=await seed(owner,model='gemini-embedding-2',processor_ids=['test:personal:embedding'])
    profiles={}
    async with owner.begin() as c:
        await c.execute(text("INSERT INTO app.processors(id,provider,backend,roles,enabled) VALUES ('test:personal:embedding','gemini','fixture','[\"embedding\"]',true),('test:personal:llm','groq','fixture','[\"query_resolution\",\"reranking\",\"generation\"]',true) ON CONFLICT DO NOTHING"))
        await c.execute(text("UPDATE app.processors SET enabled=true WHERE id IN ('test:personal:embedding','test:personal:llm')"))
        for role in ('embedding','query_resolution','reranking','generation'):
            identity=uuid4();profiles[role]=identity
            await c.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,max_attempts,enabled,capabilities_verified,account_verified,pricing_verified)
            VALUES(:id,:provider,:model,'fixture',:role,CAST(:processors AS jsonb),0,0,0,131072,4096,1,true,true,true,true)"""),{'id':identity,'provider':'gemini' if role=='embedding' else 'groq','model':'gemini-embedding-2' if role=='embedding' else 'openai/gpt-oss-20b','role':role,'processors':json.dumps(['test:personal:embedding','test:personal:llm'] if role=='generation' else ['test:personal:embedding' if role=='embedding' else 'test:personal:llm'])})
        await c.execute(text("UPDATE app.projects SET owner_user_id=:actor,repository_id=42,repository_branch='main',application_path='',sync_status='ready' WHERE id=:p"),{'actor':actor,'p':PA})
        for processor in ('test:personal:embedding','test:personal:llm'):
            await c.execute(text('INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,:processor,:actor)'),{'p':PA,'processor':processor,'actor':actor})
    async with runtime.begin() as c:
        await c.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(actor)})
        chat=await c.scalar(text('SELECT app.personal_create_conversation(:p,:profile)'),{'p':PA,'profile':profiles['generation']})
    async with owner.begin() as c:
        await c.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"),{'id':chat['id']})
    async with runtime.begin() as c:
        await c.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(actor)})
        turn=await c.scalar(text('SELECT app.personal_append_turn(CAST(:id AS uuid),:key,:message)'),{'id':chat['id'],'key':uuid4(),'message':'How does React state work?'})
    async with owner.connect() as c:
        job=await c.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:id AS uuid)'),{'id':turn['id']})
    stages=[]
    async def transport(embedding,encoded,key,**kwargs):
        payload=json.loads(encoded)
        if embedding:
            stages.append('embedding')
            return {'embedding':{'values':vector},'usageMetadata':{'promptTokenCount':100}}
        name=payload['response_format']['json_schema']['name'];stages.append(name)
        if name=='dependency_resolution': result={'uncertain':False,'dependency_ids':['react']}
        elif name=='ranking': result={'ordered_chunk_ids':[str(chunk)]}
        else: result={'kind':'answered','blocks':[{'kind':'documentation','text':'React state uses hooks.','chunk_ids':[str(chunk)]}]}
        return {'model':'openai/gpt-oss-20b','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post',transport)
    async def repository(*args):return {'id':42,'name':'repo','default_branch':'main'}
    github.repository=repository
    config={'EMBEDDING_PROFILE_ID':str(profiles['embedding']),'QUERY_PROFILE_ID':str(profiles['query_resolution']),'RERANK_PROFILE_ID':str(profiles['reranking']),'GEMINI_API_KEY':'placeholder','GROQ_API_KEY':'placeholder'}
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        def factory(context,authorize):return AnswerEngine(context,engine=worker,read_engine=runtime,config=config,generation_id=generation,authorize=authorize)
        await run_personal_job(job,engine=worker,settings=settings,client=github,generation_id=generation,answerer_factory=factory)
        async with owner.connect() as c:
            result=(await c.execute(text('SELECT status,answer,citations FROM app.turns WHERE id=CAST(:id AS uuid)'),{'id':turn['id']})).one()
            assert result.status=='completed',result
            assert 'React state uses hooks.' in result.answer
            assert result.citations[0]['chunk_id']==str(chunk)
            assert await c.scalar(text('SELECT count(*) FROM app.personal_provider_calls'))==4
        assert stages==['dependency_resolution','embedding','ranking','answer']
        # The same durable turn waits, then resumes without a second query-resolution call.
        async with owner.begin() as c:
            await c.execute(text('DELETE FROM app.document_indexes WHERE generation_id=:g'),{'g':generation})
            await c.execute(text("INSERT INTO app.catalog_jobs(catalog_revision_id,generation_id,status,stage) VALUES(:r,:g,'running','Building documentation index')"),{'r':revision,'g':generation})
        async with runtime.begin() as c:
            await c.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(actor)})
            waiting_turn=await c.scalar(text('SELECT app.personal_append_turn(CAST(:id AS uuid),:key,:message)'),{'id':chat['id'],'key':uuid4(),'message':'How do React hooks update state?'})
        async with owner.connect() as c:
            waiting_job=await c.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:id AS uuid)'),{'id':waiting_turn['id']})
        await run_personal_job(waiting_job,engine=worker,settings=settings,client=github,generation_id=generation,answerer_factory=factory)
        async with owner.begin() as c:
            assert await c.scalar(text('SELECT status FROM app.turns WHERE id=CAST(:id AS uuid)'),{'id':waiting_turn['id']})=='waiting_for_sources'
            await c.execute(text('INSERT INTO app.document_indexes(document_id,generation_id,document_version_id) SELECT document_id,:g,:v FROM app.chunks WHERE id=:chunk'),{'g':generation,'v':version,'chunk':chunk})
            await c.execute(text("UPDATE app.catalog_jobs SET status='completed' WHERE catalog_revision_id=:r"),{'r':revision})
        async with worker.begin() as c:
            assert await c.scalar(text('SELECT app.wake_personal_waits()'))==1
            assert await c.scalar(text('SELECT app.wake_personal_waits()'))==0
        await run_personal_job(waiting_job,engine=worker,settings=settings,client=github,generation_id=generation,answerer_factory=factory)
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT status FROM app.turns WHERE id=CAST(:id AS uuid)'),{'id':waiting_turn['id']})=='completed'
        assert stages.count('dependency_resolution')==2
        async with owner.begin() as c:
            await c.execute(text('UPDATE app.document_assessments SET credential_blocked=true WHERE document_version_id=:id'),{'id':version})
        async with runtime.begin() as c:
            await c.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(actor)})
            blocked=await c.scalar(text('SELECT app.personal_turn(CAST(:id AS uuid))'),{'id':turn['id']})
            assert blocked['status']=='blocked_policy' and blocked['answer'] is None
    finally:
        await worker.dispose()
