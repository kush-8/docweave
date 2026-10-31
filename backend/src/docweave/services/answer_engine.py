"""Admitted hybrid RAG using the existing search, fusion and reranking stages."""
import json
from uuid import UUID,uuid5
from docweave.core.identity import Actor
from docweave.db.sessions import tenant_session
from docweave.integrations.answers import answer_request,answer_result,resolution_request,resolution_result
from docweave.integrations.gemini import embedding_request,embedding_result
from docweave.integrations.groq import ranking_result
from docweave.rag.contracts import HostedError
from docweave.rag.fusion import fuse_channels
from docweave.rag.retrieval import retrieve_channels
from docweave.rag.reranking import bounded_ranking_request,ranked_evidence
from docweave.rag.tokenization import count_evidence_tokens
from docweave.repositories import personal as repository
from docweave.repositories.rag import scope
from docweave.services.personal_providers import dispatch

class AnswerEngine:
    def __init__(self,job,*,engine,read_engine,config,generation_id,authorize):
        self.job=job
        self.engine=engine
        self.read_engine=read_engine
        self.config=config
        self.generation_id=generation_id
        self.authorize_upstream=authorize
        self.actor=Actor(UUID(job['actor_id']))
        self.project_id=UUID(job['project']['id'])
        self.hits=[]
        self.history=None

    async def authorize(self):
        await self.authorize_upstream()
        if self.hits:
            async with tenant_session(self.read_engine,actor_id=self.actor.user_id) as session:
                collections=list({hit['collection_id'] for hit in self.hits})
                await scope.authorize(session,self.project_id,collections,self.generation_id)
                await scope.recheck(session,{'lexical':self.hits,'vector':[],'snapshot_ids':[str(hit['document_version_id']) for hit in self.hits]})

    async def profile(self,identity,role):
        if not identity:
            raise HostedError('provider_unavailable')
        async with self.engine.begin() as c:
            result=await repository.profile(c,UUID(str(identity)))
        if not result or result['role']!=role or not result['available']:
            raise HostedError('provider_unavailable')
        return result

    async def dispatch(self,payload,profile,stage,embedding=False):
        return await dispatch(payload,embedding=embedding,profile_id=UUID(profile['id']),operation_key=str(self.job['id'])+':'+stage,actor_id=self.actor.user_id,project_id=self.project_id,
            engine=self.engine,api_key=self.config.get('GEMINI_API_KEY' if embedding else 'GROQ_API_KEY'),authorize=self.authorize)

    async def context_history(self):
        if self.history is None:
            async with self.engine.begin() as c:
                items=await repository.history(c,UUID(self.job['id']),UUID(self.job['lease_token']))
            if any(item['status']=='blocked_policy' for item in items):
                raise HostedError('context_blocked')
            self.history=[]
            used=0
            for item in reversed(items):
                if item['status']!='completed':
                    continue
                pair={'message':item['message'],'answer':item['answer'],'context_revision':item['context_revision']}
                size=count_evidence_tokens(json.dumps(pair,ensure_ascii=False))
                if used+size>6000:
                    break
                self.history.insert(0,pair)
                used+=size
        return self.history

    async def resolve(self,turn,project):
        if not project['stack']:
            return []
        profile=await self.profile(self.config.get('QUERY_PROFILE_ID'),'query_resolution')
        payload=resolution_request(turn['message'],project,await self.context_history(),profile['model'])
        result=await self.dispatch(payload,profile,'query_resolution')
        return resolution_result(result,project,profile['model'])

    async def answer(self,turn,project,required):
        if not self.generation_id:
            raise HostedError('provider_unavailable')
        if len(turn['message'])>4096:
            return {'status':'completed','answer':'Please narrow the question to at most 4,096 characters so I can retrieve supporting documentation.','citations':[]}
        async with self.engine.begin() as c:
            collections=await repository.scopes(c,UUID(self.job['id']),UUID(self.job['lease_token']),self.generation_id)
        if not collections:
            return {'status':'completed','answer':'No eligible documentation is available for this project yet.','citations':[]}
        profile=await self.profile(self.config.get('EMBEDDING_PROFILE_ID'),'embedding')
        async with self.engine.begin() as c:
            if not await repository.embedding_matches(c,self.generation_id,UUID(profile['id'])):
                raise HostedError('provider_unavailable')
        query=embedding_request(turn['message'],'query')
        vector=embedding_result(await self.dispatch(query,profile,'query_embedding',embedding=True))
        channels=await retrieve_channels(self.actor,self.project_id,turn['message'],collection_ids=collections,generation_id=self.generation_id,query_vector=vector,engine=self.read_engine,
            lexical=self.config.get('RAG_LEXICAL_STRATEGY','bm25'),vector=self.config.get('RAG_VECTOR_STRATEGY','exact'))
        candidates=fuse_channels(channels)
        self.hits=candidates
        if not candidates:
            return {'status':'completed','answer':'I could not find eligible documentation supporting an answer to this question.','citations':[]}
        profile=await self.profile(self.config.get('RERANK_PROFILE_ID'),'reranking')
        wire=[{'chunk_id':str(hit['chunk_id']),'document_version_id':str(hit['document_version_id']),'quote':hit['quote']} for hit in candidates]
        payload,accepted=bounded_ranking_request(turn['message'],wire,model=profile['model'])
        if payload is None:
            return {'status':'completed','answer':'The available evidence does not fit the configured retrieval budget. Please narrow the question.','citations':[]}
        response=await self.dispatch(payload,profile,'reranking')
        ranking=ranking_result(response,[hit['chunk_id'] for hit in accepted],profile['model'])
        selected=ranked_evidence(candidates,ranking['ordered_chunk_ids'],count_evidence_tokens)
        self.hits=selected
        if not selected:
            return {'status':'completed','answer':'I do not have sufficient supporting documentation for this question.','citations':[]}
        identity=self.job['conversation'].get('answer_profile_id')
        profile=await self.profile(identity,'generation')
        wire=[{'chunk_id':str(hit['chunk_id']),'document_version_id':str(hit['document_version_id']),'quote':hit['quote']} for hit in selected]
        payload=answer_request(turn['message'],project,await self.context_history(),wire,profile['model'])
        raw=await self.dispatch(payload,profile,'generation')
        try:
            result=answer_result(raw,wire,profile['model'])
        except HostedError as error:
            if str(error)=='invalid_answer_citations':
                return {'status':'completed','answer':'I could not validate the answer references, so I am withholding that answer.','citations':[]}
            raise
        by_id={str(hit['chunk_id']):hit for hit in selected}
        citations=[]
        numbers={}
        blocks=[]
        for block in result['blocks']:
            refs=[]
            for identity in block['chunk_ids']:
                if identity not in numbers:
                    hit=by_id[identity]
                    numbers[identity]=len(citations)+1
                    citations.append({'id':str(uuid5(UUID(turn['id']),identity)),'chunk_id':identity,'document_version_id':str(hit['document_version_id']),'generation_id':str(hit['generation_id']),'title':hit['provenance'].get('document_title','Documentation'),
                        'excerpt':hit['quote'],'url':hit['source_url'],'locator':hit['locator']})
                refs.append('['+str(numbers[identity])+']')
            prefix={'documentation':'','project_context':'Project context: ','inferred_advice':'Inferred advice: '}[block['kind']]
            blocks.append(prefix+block['text']+(' '+''.join(refs) if refs else ''))
        await self.authorize()
        return {'status':'completed','answer':'\n\n'.join(blocks) or 'I do not have sufficient evidence to answer.','citations':citations}
