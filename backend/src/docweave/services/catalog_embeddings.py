"""Admit only public source embeddings matching the selected immutable generation."""
from uuid import UUID
from docweave.integrations.gemini import embedding_request,embedding_result
from docweave.rag.contracts import HostedError
from docweave.repositories import catalog as repository
from docweave.services.personal_providers import dispatch


def make_embedder(job,token,*,engine,config):
    identity=config.get('EMBEDDING_PROFILE_ID')
    if not identity or not config.get('GEMINI_API_KEY'):
        return None
    profile=UUID(identity)
    counter=0
    async def authorize():
        async with engine.begin() as c:
            if not await repository.embedding_authorized(c,UUID(job['id']),token,profile):
                raise HostedError('provider_unavailable')
            await repository.index_input(c,UUID(job['id']),token)
    async def embed(bodies):
        nonlocal counter
        vectors=[]
        for body in bodies:
            stage=counter
            counter+=1
            payload=embedding_request(body,'document')
            result=await dispatch(payload,embedding=True,profile_id=profile,operation_key='catalog:'+job['id']+':'+str(stage),actor_id=UUID('60000000-0000-4000-8000-000000000001'),project_id=None,
                engine=engine,api_key=config['GEMINI_API_KEY'],authorize=authorize)
            vectors.append(embedding_result(result))
        return vectors
    return embed
