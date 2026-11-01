"""LangChain embeddings over the same bounded, no-retry admitted transport."""
import asyncio
import json
from types import SimpleNamespace
from langchain_openai import OpenAIEmbeddings
from docweave.integrations.provider_transport import provider_post
from docweave.rag.contracts import HostedError, RetrievalError, validate_vector

API_KEY = 'OPENAI_API_KEY'
MODEL = 'text-embedding-3-small'

def embedding_request(content, kind):
    if kind not in ('query','document') or not isinstance(content,str) or not content.strip() or '\x00' in content:
        raise HostedError('invalid_embedding_input')
    # UTF-8 bytes conservatively bound tokens without downloading a tokenizer.
    if len(content.encode('utf-8'))>8192:
        raise HostedError('embedding_input_too_large')
    return {'model':MODEL,'input':[content],'dimensions':768,'encoding_format':'float'}

def embedding_result(response):
    try:
        if response['model']!=MODEL or len(response['data'])!=1 or response['data'][0]['index']!=0:
            raise ValueError
        vector=response['data'][0]['embedding']
        validate_vector(vector)
    except (KeyError,TypeError,IndexError,ValueError,RetrievalError):
        raise HostedError('invalid_embedding_response') from None
    return vector

async def embedding_post(body, api_key, *, transport=None):
    payload=json.loads(body)
    expected=embedding_request(payload['input'][0],'document')
    if payload!=expected:
        raise HostedError('invalid_embedding_input')
    result=None
    async def create(**request):
        nonlocal result
        # LangChain must not change the body already hashed and charged by admission.
        if request!=payload or result is not None:
            raise HostedError('embedding_request_changed')
        result=await provider_post(True,body,api_key,transport=transport,provider='openai')
        embedding_result(result)
        return result
    embeddings=OpenAIEmbeddings(model=MODEL,dimensions=768,api_key=api_key,
        client=object(),async_client=SimpleNamespace(create=create),
        max_retries=0,chunk_size=1,check_embedding_ctx_length=False,
        model_kwargs={'encoding_format':'float'})
    async with asyncio.timeout(45):
        await embeddings.aembed_query(payload['input'][0])
    return result
