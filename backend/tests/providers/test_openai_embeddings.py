"""Real LangChain orchestration with bounded, mocked provider HTTP."""
import json
import httpx
import pytest
from docweave.rag.contracts import HostedError

pytestmark = pytest.mark.anyio

def basis():
    return [1.0] + [0.0] * 767

async def test_langchain_uses_one_exact_admitted_request_and_preserves_usage():
    from docweave.integrations.openai import embedding_request, embedding_post, embedding_result
    calls=[]
    def handler(request):
        calls.append(request)
        assert str(request.url)=='https://api.openai.com/v1/embeddings'
        assert request.headers['authorization']=='Bearer fixture'
        assert json.loads(request.content)==payload
        return httpx.Response(200,json={'model':'text-embedding-3-small','data':[{'index':0,'embedding':basis()}],
            'usage':{'prompt_tokens':2,'total_tokens':2}})
    payload=embedding_request('hello world','document')
    assert payload=={'model':'text-embedding-3-small','input':['hello world'],'dimensions':768,'encoding_format':'float'}
    raw=await embedding_post(json.dumps(payload).encode(),'fixture',transport=httpx.MockTransport(handler))
    assert embedding_result(raw)==basis()
    assert raw['usage']['prompt_tokens']==2
    assert len(calls)==1

async def test_langchain_does_not_retry_failed_calls():
    from docweave.integrations.openai import embedding_request, embedding_post
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,json={'error':'capacity'})
    with pytest.raises(HostedError):
        await embedding_post(json.dumps(embedding_request('hello','query')).encode(),'fixture',transport=httpx.MockTransport(handler))
    assert len(calls)==1

@pytest.mark.parametrize('content',['','  ','a\x00b','a'*8193])
async def test_invalid_input_is_rejected_before_http(content):
    from docweave.integrations.openai import embedding_request
    with pytest.raises(HostedError):
        embedding_request(content,'query')

@pytest.mark.parametrize('changes',[{'model':'other'},{'data':[]},{'data':[{'index':1,'embedding':basis()}]},
    {'data':[{'index':0,'embedding':[0.0]*768}]},{'data':[{'index':0,'embedding':basis()}]*2}])
async def test_response_must_match_model_single_input_and_unit_vector(changes):
    from docweave.integrations.openai import embedding_result
    with pytest.raises(HostedError):
        embedding_result({'model':'text-embedding-3-small','data':[{'index':0,'embedding':basis()}],**changes})

async def test_provider_selection_is_explicit():
    from docweave.integrations.embeddings import embedding_backend
    assert embedding_backend({'EMBEDDING_PROVIDER':'openai'}).API_KEY=='OPENAI_API_KEY'
    assert embedding_backend({}).API_KEY=='GEMINI_API_KEY'
    with pytest.raises(HostedError):
        embedding_backend({'EMBEDDING_PROVIDER':'other'})

async def test_catalog_and_answer_callers_choose_openai_only_for_embeddings(monkeypatch):
    from contextlib import asynccontextmanager
    from uuid import uuid4
    from docweave.services import catalog_embeddings, answer_engine
    calls=[]
    async def dispatch(payload,**options):
        calls.append((payload,options))
        return {'model':'text-embedding-3-small','data':[{'index':0,'embedding':basis()}]}
    monkeypatch.setattr(catalog_embeddings,'dispatch',dispatch)
    monkeypatch.setattr(answer_engine,'dispatch',dispatch)
    async def policy(*args): return {'epoch':1}
    monkeypatch.setattr(answer_engine,'current_policy',policy)
    class Engine:
        @asynccontextmanager
        async def begin(self): yield None
    config={'EMBEDDING_PROVIDER':'openai','OPENAI_API_KEY':'embedding-key','GROQ_API_KEY':'llm-key',
        'GEMINI_API_KEY':'legacy-key','EMBEDDING_PROFILE_ID':str(uuid4())}
    embed=catalog_embeddings.make_embedder({'id':str(uuid4())},uuid4(),engine=None,config=config)
    assert await embed(['public documentation'])==[basis()]
    assert calls[-1][0]['input']==['public documentation']
    assert calls[-1][1]['api_key']=='embedding-key'
    engine=answer_engine.AnswerEngine({'id':str(uuid4()),'actor_id':str(uuid4()),'project':{'id':str(uuid4())}},
        engine=Engine(),read_engine=None,config=config,generation_id=uuid4(),authorize=None)
    profile={'id':str(uuid4()),'model':'openai/gpt-oss-20b'}
    await engine.dispatch({'model':'text-embedding-3-small'},profile,'query_embedding',embedding=True)
    assert calls[-1][1]['api_key']=='embedding-key'
    await engine.dispatch({'model':'openai/gpt-oss-20b','messages':[{}, {'content':json.dumps({'evidence':[]})}]},profile,'generation')
    assert calls[-1][1]['api_key']=='llm-key'
