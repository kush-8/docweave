"""OpenAI uses the real durable accounting path, with no paid HTTP."""
from decimal import Decimal
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import text
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.integrations.openai import embedding_request
from docweave.rag.contracts import HostedError
from docweave.services.personal_providers import dispatch
from tests.database.test_database import A, PA, databases, test_urls

pytestmark=pytest.mark.anyio

@pytest.mark.parametrize('success',[True,False])
async def test_openai_metering_reuse_consent_and_unknown_completion(databases,success):
    owner,_=databases
    identity=uuid4()
    async with owner.begin() as c:
        await c.execute(text("INSERT INTO app.processors(id,provider,backend,roles,enabled) VALUES('test:openai:dispatch','openai','openai-api','[\"embedding\"]',true)"))
        await c.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,max_attempts,enabled,capabilities_verified,account_verified,pricing_verified)
            VALUES(:id,'openai','text-embedding-3-small','openai-api','embedding','["test:openai:dispatch"]',0.02,0,0,16384,0,1,true,true,true,true)"""),{'id':identity})
        await c.execute(text('UPDATE app.projects SET owner_user_id=:a WHERE id=:p'),{'a':A,'p':PA})
        await c.execute(text("INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,'test:openai:dispatch',:a)"),{'a':A,'p':PA})
        chat=await c.scalar(text("INSERT INTO app.conversations(project_id,status) VALUES(:p,'ready') RETURNING id"),{'p':PA})
        job=await c.scalar(text("INSERT INTO app.personal_jobs(conversation_id,actor_id,kind,status,lease_token,lease_expires_at) VALUES(:c,:a,'answer','running',gen_random_uuid(),now()+interval '10 minutes') RETURNING id"),{'c':chat,'a':A})
    calls=[]
    def handler(request):
        calls.append(request)
        if not success:
            return httpx.Response(429,json={'error':'capacity'})
        return httpx.Response(200,json={'model':'text-embedding-3-small','data':[{'index':0,'embedding':[1.0]+[0.0]*767}],
            'usage':{'prompt_tokens':2,'total_tokens':2}})
    checks=[]
    async def authorize():
        checks.append(True)
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    options=dict(embedding=True,profile_id=identity,operation_key=str(job)+':query_embedding',actor_id=A,project_id=PA,
        engine=worker,api_key='fixture',authorize=authorize,transport=httpx.MockTransport(handler))
    payload=embedding_request('hello world','query')
    try:
        if success:
            first=await dispatch(payload,**options)
            assert await dispatch(payload,**options)==first
            async with owner.begin() as c:
                charge=(await c.execute(text('SELECT status,actual_usd FROM app.cost_reservations'))).one()
                assert charge.status=='metered' and charge.actual_usd==Decimal('0.00000004')
                await c.execute(text("DELETE FROM app.project_processor_approvals WHERE processor_id='test:openai:dispatch'"))
            with pytest.raises(HostedError,match='provider_unavailable'):
                await dispatch(payload,**options)
        else:
            for _ in range(2):
                with pytest.raises(HostedError,match='completion_unknown'):
                    await dispatch(payload,**options)
            async with owner.connect() as c:
                assert await c.scalar(text('SELECT status FROM app.cost_reservations'))=='uncertain'
        assert len(calls)==1
        assert len(checks)>=3
    finally:
        await worker.dispose()
        async with owner.begin() as c:
            await c.execute(text('TRUNCATE app.project_processor_approvals,app.collection_processor_approvals,app.processors'))
