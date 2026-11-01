"""Coverage decisions use real owner sessions and guarded disposable PostgreSQL."""
import json
from uuid import UUID
import pytest
from sqlalchemy import text
from tests.support.personal import collections
from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls

pytestmark = pytest.mark.anyio


async def revision(connection, *, approved=True, granularity='major', version='1', technology='fast-api'):
    return await connection.scalar(text("""INSERT INTO app.public_catalog_revisions
        (technology,ecosystem,docs_target,coverage,origin,path_prefix,source_url,attribution,source_hash,enabled,source_approved,package_aliases)
        VALUES (:technology,'python',:version,CAST(:coverage AS jsonb),'https://docs.example.org','/v1/',
        'https://docs.example.org/v1/guide.md','Publisher documentation',:hash,true,:approved,'["fastapi"]') RETURNING id"""),
        {'technology': technology, 'version': version, 'coverage': json.dumps({'granularity': granularity, 'version': version}), 'hash': 'a' * 64, 'approved': approved})


async def setup(c):
    async with c['owner'].begin() as connection:
        await connection.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:project'),
            {'project': UUID(c['project']), 'stack': json.dumps([{'id': 'dep', 'technology': 'FastAPI', 'ecosystem': 'python', 'docs_target': '1.2.3', 'direct': True, 'role': 'runtime'}])})
        return await revision(connection)


async def test_project_coverage_requires_explicit_fallback_acceptance_and_current_context(collections):
    c = collections
    candidate = await setup(c)
    path = f"/api/v1/projects/{c['project']}/documentation"
    response = await c['admin'].get(path)
    assert response.status_code == 200, response.text
    coverage = response.json()
    assert coverage['items'][0]['status'] == 'pending_review'
    selection = {'expected_revision': coverage['context_revision'], 'revision_id': str(candidate)}
    assert (await c['admin'].put(path + '/dep', json=selection, headers=c['headers'])).status_code == 422
    response = await c['admin'].put(path + '/dep', json={**selection, 'accept_fallback': True}, headers=c['headers'])
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['items'][0]['status'] == 'capacity'
    assert updated['items'][0]['selected_revision_id'] == str(candidate)
    assert updated['context_revision'] == coverage['context_revision'] + 1
    assert (await c['admin'].put(path + '/dep', json={**selection, 'accept_fallback': True}, headers=c['headers'])).status_code == 409
    async with c['owner'].begin() as connection:
        await connection.execute(text("UPDATE app.projects SET stack=jsonb_set(stack,'{0,docs_target}','\"1.3.0\"'),context_revision=context_revision+1 WHERE id=:id"), {'id': UUID(c['project'])})
    assert (await c['admin'].get(path)).json()['items'][0]['status'] == 'pending_review'


async def test_coverage_ownership_csrf_unknown_and_revoked_sources(collections):
    c = collections
    await setup(c)
    async with c['owner'].begin() as connection:
        candidate = await revision(connection, approved=False, granularity='exact', version='1.2.3')
    path = f"/api/v1/projects/{c['project']}/documentation"
    assert (await c['guest'].get(path)).status_code == 404
    body = {'expected_revision': 1, 'revision_id': str(candidate)}
    assert (await c['admin'].put(path + '/dep', json=body)).status_code == 403
    assert (await c['admin'].put(path + '/dep', json=body, headers=c['headers'])).status_code == 422
    assert (await c['guest'].put(path + '/dep', json=body, headers=c['guest_headers'])).status_code == 404
    item = (await c['admin'].get(path)).json()['items'][0]
    assert item['status'] == 'pending_review'
    assert item['reason'] == 'source approval required'
    async with c['owner'].begin() as connection:
        await connection.execute(text('UPDATE app.public_catalog_revisions SET enabled=false WHERE id=:id'), {'id': candidate})
    assert all(row['entry']['revision_id'] != str(candidate) for row in (await c['admin'].get(path)).json()['items'][0]['candidates'])


async def test_fallback_retrieval_rechecks_exact_accepted_target_and_revocation(databases):
    from tests.personal.test_personal_retrieval import seed
    from tests.database.test_database import A, PA
    from docweave.db.sessions import domain_session
    from docweave.repositories import personal as repository
    from docweave.rag.retrieval import retrieve_channels
    from docweave.rag.contracts import RetrievalError
    from docweave.core.identity import Actor
    owner, runtime = databases
    generation, candidate, collection, version, chunk, vector = await seed(owner, coverage={'granularity': 'major', 'version': '19'})
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.projects SET stack=jsonb_set(stack,'{0,docs_target}','\"19.1.0\"') WHERE id=:id"), {'id': PA})
    with pytest.raises(RetrievalError):
        await retrieve_channels(Actor(A), PA, 'React', collection_ids=[collection], generation_id=generation, query_vector=vector, engine=runtime)
    async with domain_session(runtime, A) as connection:
        await repository.choose_documentation(connection, PA, 'react', 1, candidate, True, generation)
    found = await retrieve_channels(Actor(A), PA, 'React', collection_ids=[collection], generation_id=generation, query_vector=vector, engine=runtime)
    assert found['lexical'][0]['chunk_id'] == chunk
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.projects SET stack=jsonb_set(stack,'{0,docs_target}','\"19.2.0\"') WHERE id=:id"), {'id': PA})
    with pytest.raises(RetrievalError):
        await retrieve_channels(Actor(A), PA, 'React', collection_ids=[collection], generation_id=generation, query_vector=vector, engine=runtime)
    async with domain_session(runtime, A) as connection:
        await repository.choose_documentation(connection, PA, 'react', 2, candidate, True, generation)
    async with owner.begin() as connection:
        await connection.execute(text('UPDATE app.public_catalog_revisions SET source_approved=false WHERE id=:id'), {'id': candidate})
    with pytest.raises(RetrievalError):
        await retrieve_channels(Actor(A), PA, 'React', collection_ids=[collection], generation_id=generation, query_vector=vector, engine=runtime)


async def test_catalog_reports_only_active_work_as_processing_and_deduplicates_selection_jobs(collections):
    c = collections
    candidate = await setup(c)
    async with c['owner'].begin() as connection:
        generation = await connection.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES('fixture','fixture',768,'unit-l2','fixture','[\"fixture\"]',true) RETURNING id"))
    c['data']['app'].state.runtime_config['RAG_GENERATION_ID'] = str(generation)
    path = f"/api/v1/projects/{c['project']}/documentation"
    body = {'expected_revision': 1, 'revision_id': str(candidate), 'accept_fallback': True}
    response = await c['admin'].put(path + '/dep', json=body, headers=c['headers'])
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['status'] == 'waiting_for_sources'
    body['expected_revision'] = 2
    assert (await c['admin'].put(path + '/dep', json=body, headers=c['headers'])).json()['context_revision'] == 2
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.catalog_jobs')) == 1
    for status, expected in [('capacity', 'capacity'), ('failed', 'failed'), ('pending_review', 'pending_review'), ('blocked_policy', 'pending_review'), ('completed', 'missing')]:
        async with c['owner'].begin() as connection:
            await connection.execute(text('UPDATE app.catalog_jobs SET status=:status'), {'status': status})
        item = (await c['admin'].get(path)).json()['items'][0]
        assert item['status'] == expected
        assert not item['entry']['active_job']
    response = await c['admin'].put(path + '/dep', json={'expected_revision': 2}, headers=c['headers'])
    assert response.status_code == 200 and response.json()['items'][0]['status'] == 'missing'
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.catalog_jobs')) == 1


async def test_operator_review_creates_replacement_revision_without_runtime_publication(databases, test_urls, tmp_path, monkeypatch):
    from docweave.catalog import review
    from docweave.repositories.catalog import publish_manifest
    from docweave.services.catalog_review import parse_manifest
    from tests.rag.test_catalog_manifest import manifest
    owner, runtime = databases
    file = tmp_path / 'sources.json'
    file.write_text(json.dumps(manifest()), encoding='utf-8')
    monkeypatch.setenv('CATALOG_TEST_URL', test_urls[1].render_as_string(hide_password=False))
    dry = await review(file)
    candidate = await review(file, apply=True, url_env='CATALOG_TEST_URL')
    with pytest.raises(ValueError):
        await review(file, apply=True, approve_hash='0' * 64, url_env='CATALOG_TEST_URL')
    approved = await review(file, apply=True, approve_hash=dry['manifest_hash'], url_env='CATALOG_TEST_URL')
    repeated = await review(file, apply=True, approve_hash=dry['manifest_hash'], url_env='CATALOG_TEST_URL')
    assert approved == repeated
    assert approved['revision_ids'] != candidate['revision_ids']
    async with owner.connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.public_catalog_revisions WHERE enabled AND source_approved')) == 1
        assert await connection.scalar(text('SELECT count(*) FROM app.catalog_jobs')) == 0
    entries, digest = parse_manifest(manifest())
    with pytest.raises(ValueError):
        async with runtime.begin() as connection:
            await publish_manifest(connection, entries, digest, approved=True)
    revoked = await review(apply=True, revoke=UUID(approved['revision_ids'][0]), url_env='CATALOG_TEST_URL')
    assert revoked['revoked']
    with pytest.raises(ValueError, match='revoked'):
        await review(file, apply=True, approve_hash=dry['manifest_hash'], url_env='CATALOG_TEST_URL')


async def test_removing_an_exact_selection_survives_automatic_reconciliation(collections):
    c = collections
    await setup(c)
    async with c['owner'].begin() as connection:
        candidate = await revision(connection, granularity='exact', version='1.2.3')
    path = f"/api/v1/projects/{c['project']}/documentation"
    selected = await c['admin'].put(path + '/dep', json={'expected_revision': 1, 'revision_id': str(candidate)}, headers=c['headers'])
    assert selected.status_code == 200
    removed = await c['admin'].put(path + '/dep', json={'expected_revision': 2}, headers=c['headers'])
    assert removed.status_code == 200
    async with c['owner'].begin() as connection:
        await connection.execute(text('SELECT app.personal_reconcile_catalog(:project,:actor,CAST(:choices AS jsonb),NULL)'),
            {'project': UUID(c['project']), 'actor': UUID(c['user']['id']), 'choices': json.dumps([{'dependency_id': 'dep', 'revision_id': str(candidate)}])})
    current = (await c['admin'].get(path)).json()['items'][0]
    assert current['selected_revision_id'] is None
    assert current['status'] == 'missing'
    assert current['reason'] == 'documentation selection removed'


@pytest.mark.parametrize('change', ['remove', 'version', 'disable_generation'])
async def test_retained_citations_and_history_obey_current_project_coverage(databases, change):
    from uuid import uuid4
    from tests.personal.test_personal_retrieval import seed
    from tests.database.test_database import A, PA
    from docweave.db.sessions import domain_session
    from docweave.repositories import personal as repository
    owner, runtime = databases
    generation, candidate, collection, version, chunk, vector = await seed(owner, coverage={'granularity': 'major', 'version': '19'})
    async with domain_session(runtime, A) as connection:
        await repository.choose_documentation(connection, PA, 'react', 1, candidate, True, generation)
    citations = [{'id': 'source', 'chunk_id': str(chunk), 'document_version_id': str(version),
        'generation_id': str(generation), 'excerpt': 'React state uses hooks.'}]
    async with owner.begin() as connection:
        chat = await connection.scalar(text("INSERT INTO app.conversations(project_id,status) VALUES(:project,'ready') RETURNING id"), {'project': PA})
        turn = await connection.scalar(text("INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message,status,answer,citations) VALUES(:chat,1,:key,'Question','completed','Supported answer',CAST(:citations AS jsonb)) RETURNING id"),
            {'chat': chat, 'key': uuid4(), 'citations': json.dumps(citations)})
    async with domain_session(runtime, A) as connection:
        assert (await repository.turn(connection, turn))['answer'] == 'Supported answer'
        assert await repository.citation(connection, turn, 'source')
    if change == 'remove':
        async with domain_session(runtime, A) as connection:
            await repository.choose_documentation(connection, PA, 'react', 2, None, False, generation)
    elif change == 'version':
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.projects SET stack=jsonb_set(stack,'{0,docs_target}','\"19.1.0\"') WHERE id=:id"), {'id': PA})
    else:
        async with owner.begin() as connection:
            await connection.execute(text('UPDATE app.index_generations SET enabled=false WHERE id=:id'), {'id': generation})
    async with domain_session(runtime, A) as connection:
        hidden = await repository.turn(connection, turn)
        assert hidden['status'] == 'blocked_policy' and hidden['answer'] is None
        assert await repository.citation(connection, turn, 'source') is None
    async with owner.connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.document_indexes WHERE generation_id=:id'), {'id': generation}) == 1
