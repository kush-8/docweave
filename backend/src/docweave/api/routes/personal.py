"""Personal project transport; repository visibility is checked before private release."""
from uuid import UUID
from uuid import uuid4
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from docweave.api.routes.github_auth import github_service, require_github_user, require_github_csrf
from docweave.core.errors import DomainError
from docweave.core.pagination import decode_cursor, page
from docweave.db.sessions import domain_session
from docweave.repositories import personal as repository
from docweave.schemas.personal import PersonalProjectCreate, RepositorySetup,ProcessingPolicyInput,DocumentReviewInput,DocumentationChoiceInput
from docweave.schemas.personal import PublisherLookupInput, PrivateSourceReviewInput
from docweave.services.catalog import documentation_coverage
from docweave.services.source_review import seal_candidate, open_candidate, review_values
from docweave.repositories import ingestion as ingestion_repository
from docweave.rag.contracts import CONFIGURATION

router=APIRouter(prefix='/api/v1',tags=['Projects'])

async def project_access(request,user,identity):
    _,engine,client=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        result=await repository.project(session,identity)
    if result is None:
        raise HTTPException(404)
    if result['repository']:
        await client.repository(request.state.github_token,result['repository']['repository_id'])
    return result

@router.get('/projects')
async def list_projects(request:Request,limit:int=Query(25,ge=1,le=100),cursor:str|None=Query(None,max_length=2048),user=Depends(require_github_user)):
    settings,engine,client=github_service(request)
    after,identity=decode_cursor(settings,cursor,user['id'],'personal-projects:v1')
    async with domain_session(engine,UUID(user['id'])) as session:
        rows=await repository.list_projects(session,after,identity,limit+1)
    result=page(settings,rows,limit,user['id'],'personal-projects:v1')
    for item in result['items']:
        if item['repository']:
            await client.repository(request.state.github_token,item['repository']['repository_id'])
    return result

@router.post('/projects',status_code=201)
async def create_project(body:PersonalProjectCreate,request:Request,user=Depends(require_github_csrf)):
    _,engine,client=github_service(request)
    repo=await client.repository(request.state.github_token,body.repository_id)
    values=body.model_dump()
    values['name']=body.name or repo['name']
    values['branch']=body.branch or repo['default_branch']
    await client.head(request.state.github_token,body.repository_id,values['branch'])
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.create_project(session,values)

@router.get('/projects/{project_id}')
async def get_project(project_id:UUID,request:Request,user=Depends(require_github_user)):
    return await project_access(request,user,project_id)

@router.post('/projects/{project_id}/repository')
async def link_repository(project_id:UUID,body:RepositorySetup,request:Request,user=Depends(require_github_csrf)):
    await project_access(request,user,project_id)
    _,engine,client=github_service(request)
    repo=await client.repository(request.state.github_token,body.repository_id)
    values=body.model_dump()
    values['branch']=body.branch or repo['default_branch']
    await client.head(request.state.github_token,body.repository_id,values['branch'])
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.link_repository(session,project_id,values)

@router.get('/catalog')
async def catalog(request:Request):
    _,engine,_=github_service(request)
    async with engine.connect() as session:
        return {'items':await repository.catalog(session, catalog_generation(request)),'next_cursor':None}


@router.get('/catalog/references')
async def catalog_references():
    from docweave.services.reference_catalog import reference_catalog
    return reference_catalog()


def catalog_generation(request):
    value = request.app.state.runtime_config.get('RAG_GENERATION_ID')
    return UUID(value) if value else None


async def project_documentation(request, user, project_id):
    project = await project_access(request, user, project_id)
    _, engine, _ = github_service(request)
    generation = catalog_generation(request)
    async with domain_session(engine, UUID(user['id'])) as session:
        entries = await repository.catalog(session, generation)
        entries += await repository.private_source_entries(session, project_id, generation)
    return {'context_revision': project['context_revision'], 'generation_id': str(generation) if generation else None,
        'items': documentation_coverage(project, entries, str(generation) if generation else '')}


@router.get('/projects/{project_id}/documentation')
async def documentation(project_id:UUID, request:Request, user=Depends(require_github_user)):
    return await project_documentation(request, user, project_id)


@router.put('/projects/{project_id}/documentation/{dependency_id}')
async def choose_documentation(project_id:UUID, dependency_id:str, body:DocumentationChoiceInput, request:Request, user=Depends(require_github_csrf)):
    await project_access(request, user, project_id)
    if not dependency_id or len(dependency_id) > 200:
        raise HTTPException(422)
    _, engine, _ = github_service(request)
    async with domain_session(engine, UUID(user['id'])) as session:
        await repository.choose_documentation(session, project_id, dependency_id, body.expected_revision,
            body.revision_id, body.accept_fallback, catalog_generation(request))
    return await project_documentation(request, user, project_id)


def review_dependency(project, dependency_id, expected):
    if project['context_revision'] != expected:
        raise DomainError('revision_conflict')
    dependency = next((item for item in project['stack'] if item['id'] == dependency_id), None)
    if dependency is None or not dependency.get('docs_target'):
        raise DomainError('invalid_request')
    return dependency


@router.post('/projects/{project_id}/documentation/{dependency_id}/discover')
async def discover_documentation(project_id:UUID, dependency_id:str, body:PublisherLookupInput, request:Request, user=Depends(require_github_csrf)):
    from docweave.integrations.publisher_metadata import discover_publisher
    project = await project_access(request, user, project_id)
    dependency = review_dependency(project, dependency_id, body.expected_revision)
    settings, engine, _ = github_service(request)
    async def authorize():
        current = await project_access(request, user, project_id)
        review_dependency(current, dependency_id, body.expected_revision)
    async with engine.connect() as connection:
        locked = await ingestion_repository.acquire_worker_lock(connection)
        await connection.commit()
        if not locked:
            raise DomainError('not_ready')
        try:
            candidates = await discover_publisher(dependency, consent=body.allow_public_lookup, authorize=authorize)
            await authorize()
        except ValueError:
            raise DomainError('invalid_request') from None
        finally:
            await ingestion_repository.release_worker_lock(connection)
            await connection.commit()
    return {'context_revision': project['context_revision'], 'items': [
        {**candidate, 'candidate_token': seal_candidate(settings.encryption_key, user['id'], project, dependency, candidate)}
        for candidate in candidates]}


@router.post('/projects/{project_id}/documentation/{dependency_id}/review-source', status_code=202)
async def review_private_source(project_id:UUID, dependency_id:str, body:PrivateSourceReviewInput, request:Request, user=Depends(require_github_csrf)):
    project = await project_access(request, user, project_id)
    dependency = review_dependency(project, dependency_id, body.expected_revision)
    settings, engine, _ = github_service(request)
    try:
        candidate = open_candidate(settings.encryption_key, body.candidate_token, user['id'], project, dependency_id)
        values = review_values(dependency, candidate, body.coverage.model_dump(), body.accept_fallback)
    except (ValueError, KeyError):
        raise DomainError('invalid_request') from None
    async with domain_session(engine, UUID(user['id'])) as session:
        selection = await repository.review_source(session, project_id, dependency_id, body.expected_revision, values)
        media = 'text/markdown' if values['source_url'].endswith(('.md', '.markdown')) else 'text/plain'
        result = await ingestion_repository.enqueue_source(session, {'job': uuid4(), 'collection': UUID(selection['collection_id']),
            'selection': UUID(selection['selection_id']), 'title': dependency['technology'] + ' documentation',
            'hash': hashlib.sha256(values['source_url'].encode()).hexdigest(), 'config': CONFIGURATION + ':' + media,
            'media': media, 'request': UUID(request.state.request_id)})
    return {'selection_id': selection['selection_id'], 'job_id': result['job_id'], 'status_url': f"/api/v1/jobs/{result['job_id']}"}


@router.get('/projects/{project_id}/processing-policy')
async def processing_policy(project_id:UUID,request:Request,user=Depends(require_github_user)):
    await project_access(request,user,project_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        result=await repository.processing_policy(session,project_id)
        result['available_processors']=await repository.processors(session)
        return result

@router.put('/projects/{project_id}/processing-policy')
async def replace_processing_policy(project_id:UUID,body:ProcessingPolicyInput,request:Request,user=Depends(require_github_csrf)):
    await project_access(request,user,project_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.replace_processing_policy(session,project_id,body.expected_revision,body.approved_processor_ids)


async def document_access(request,user,identity):
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        resource=await repository.resource(session,'document',identity)
    if resource is None:
        raise HTTPException(404)
    await project_access(request,user,UUID(resource['project_id']))

@router.get('/documents/{document_id}/assessment')
async def document_assessment(document_id:UUID,request:Request,user=Depends(require_github_user)):
    await document_access(request,user,document_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        result=await repository.assessment(session,document_id)
    if result is None:
        raise HTTPException(404)
    return result

@router.get('/documents/{document_id}/review')
async def review_content(document_id:UUID,request:Request,offset:int=Query(0,ge=0,le=2000000),user=Depends(require_github_user)):
    import json
    from docweave.api.dependencies.storage import storage
    assessment=await document_assessment(document_id,request,user)
    parsed=json.loads(storage(request).read(assessment['document_version_id']))
    return {**assessment,'text':parsed['text'][offset:offset+16000],'next_offset':offset+16000 if len(parsed['text'])>offset+16000 else None}

@router.post('/documents/{document_id}/review')
async def review_document(document_id:UUID,body:DocumentReviewInput,request:Request,user=Depends(require_github_csrf)):
    await document_access(request,user,document_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        await repository.review_document(session,document_id,body.document_version_id,body.content_hash,body.rule_revision)
    return {'status':'approved_for_processing','document_version_id':body.document_version_id}
