"""Durable continuation of approved private parsed artifacts through the shared indexer."""
import asyncio
import hashlib
import json
import time
from uuid import UUID
from cryptography.fernet import Fernet
from docweave.core.identity import Actor
from docweave.core.errors import DomainError
from docweave.integrations.embeddings import embedding_backend
from docweave.rag.contracts import HostedError, RetrievalError
from docweave.rag.indexing import index_document
from docweave.repositories import private_indexing as repository, catalog
from docweave.services.personal_providers import dispatch

async def enqueue_document_index(actor,document_id,generation_id,engine):
    if generation_id is None:
        return None
    async with engine.begin() as c:
        return await repository.enqueue(c,actor.user_id,document_id,generation_id)

async def reconcile_private_indexes(engine,generation_id):
    if generation_id is None:
        return 0
    async with engine.begin() as c:
        return await repository.reconcile(c,generation_id)

async def run_private_index_job(job_id,*,engine,store,settings,client,config,embedder=None):
    async with engine.begin() as c:
        job=await repository.claim(c,job_id)
    if not job:
        return
    token=UUID(job['lease_token'])
    status='capacity'
    interrupted=False
    try:
        profile=UUID(config['EMBEDDING_PROFILE_ID'])
        backend=embedding_backend(config)
        if not config.get(backend.API_KEY) or str(config.get('RAG_GENERATION_ID'))!=job['generation_id']:
            return
        ordinal=0
        key=None
        async def authorize():
            async with engine.begin() as c:
                context=await repository.context(c,job_id,token,profile,key)
            if context is None:
                raise HostedError('provider_unavailable')
            credentials=json.loads(Fernet(settings.encryption_key).decrypt(context['encrypted_token'].encode()))
            if credentials.get('expires_at',float('inf'))<=time.time():
                raise HostedError('provider_unavailable')
            access=credentials['access_token']
            identity=await client.user(access)
            if str(identity['id'])!=context['github_subject']:
                raise HostedError('provider_unavailable')
            await client.repository(access,context['repository_id'])
            # Recheck after the access requests so revocation during HTTP cannot authorize dispatch.
            async with engine.begin() as c:
                if await repository.context(c,job_id,token,profile,key) is None:
                    raise HostedError('provider_unavailable')
        async def hosted_embed(bodies):
            nonlocal ordinal,key
            vectors=[]
            for body in bodies:
                operation='private-index:'+str(job_id)+':'+str(ordinal)
                ordinal+=1
                key=hashlib.sha256(operation.encode()).hexdigest()
                result=await dispatch(backend.embedding_request(body,'document'),embedding=True,profile_id=profile,
                    operation_key=operation,actor_id=UUID(job['actor_id']),project_id=UUID(job['project_id']),
                    engine=engine,api_key=config[backend.API_KEY],authorize=authorize)
                vectors.append(backend.embedding_result(result))
            return vectors
        await authorize()
        await index_document(Actor(UUID(job['actor_id'])),UUID(job['document_id']),UUID(job['generation_id']),
            worker_engine=engine,store=store,embedder=embedder or hosted_embed,authorize=authorize)
        status='completed'
    except asyncio.CancelledError:
        interrupted=True
        # Keep the durable lease; reconciliation resumes the original paid operation keys.
        raise
    except HostedError as error:
        status='completion_unknown' if str(error)=='completion_unknown' else 'capacity'
    except RetrievalError:
        status='capacity'
    except (DomainError,ValueError,KeyError):
        status='capacity'
    except Exception:
        status='failed'
    finally:
        if not interrupted:
            async with engine.begin() as c:
                if await repository.finish(c,job_id,token,status):
                    await catalog.wake_waits(c)
