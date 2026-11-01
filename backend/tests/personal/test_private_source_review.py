import json
from uuid import UUID
import pytest
from sqlalchemy import text
from tests.support.personal import collections
from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls

pytestmark=pytest.mark.anyio


async def test_private_source_discovery_review_is_bound_and_never_publishes_catalog(collections, monkeypatch, tmp_path):
    c=collections
    async with c['owner'].begin() as connection:
        await connection.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:id'),
            {'id': UUID(c['project']), 'stack': json.dumps([{'id':'dep','technology':'example','ecosystem':'python','docs_target':'1.2.3'}])})
    calls=[]
    async def discover(dependency, *, authorize, consent):
        assert consent is True
        await authorize()
        calls.append(dependency['technology'])
        return [{'source_url':'https://docs.example.org/v1/guide.md','origin':'https://docs.example.org','path_prefix':'/v1/',
            'attribution':'Example publisher','registry_url':'https://pypi.org/pypi/example/1.2.3/json'}]
    monkeypatch.setattr('docweave.integrations.publisher_metadata.discover_publisher',discover)
    path=f"/api/v1/projects/{c['project']}/documentation/dep"
    lookup={'expected_revision':1,'allow_public_lookup':True}
    assert (await c['admin'].post(path+'/discover',json={'expected_revision':1},headers=c['headers'])).status_code==422
    assert not calls
    response=await c['admin'].post(path+'/discover',json=lookup,headers=c['headers'])
    assert response.status_code==200,response.text
    token=response.json()['items'][0]['candidate_token']
    review={'expected_revision':1,'candidate_token':token,'coverage':{'granularity':'major','version':'1'},'accept_fallback':True}
    assert (await c['guest'].post(path+'/review-source',json=review,headers=c['guest_headers'])).status_code==404
    assert (await c['admin'].post(path+'/review-source',json=review)).status_code==403
    assert (await c['admin'].post(path+'/review-source',json={**review,'accept_fallback':False},headers=c['headers'])).status_code==422
    accepted=await c['admin'].post(path+'/review-source',json=review,headers=c['headers'])
    assert accepted.status_code==202,accepted.text
    assert (await c['admin'].post(path+'/review-source',json=review,headers=c['headers'])).status_code==409
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.public_catalog_revisions'))==0
        assert await connection.scalar(text('SELECT count(*) FROM app.ingestion_jobs'))==1
        selection=(await connection.execute(text('SELECT project_id,approved_stack,coverage FROM app.documentation_selections WHERE id=:id'),{'id':UUID(accepted.json()['selection_id'])})).one()
        assert str(selection.project_id)==c['project'] and selection.approved_stack['id']=='dep'
    coverage=(await c['admin'].get(path.rsplit('/dep',1)[0])).json()
    assert coverage['items'][0]['status']=='waiting_for_sources'
    assert coverage['items'][0]['entry']['private_selection'] is True
    from docweave.core.settings import database_url
    from docweave.db.engine import make_engine
    from docweave.services.ingestion import run_ingestion
    from docweave.storage.artifacts import ArtifactStore
    from docweave.rag.parsing import parse_text
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    async def fetcher(selection):
        return b'<main><h1>Example API</h1><p>Use the documented method.</p></main>','text/html'
    try:
        await run_ingestion(UUID(accepted.json()['job_id']),engine=worker,store=ArtifactStore(tmp_path),parser=parse_text,fetcher=fetcher)
    finally:
        await worker.dispose()
    async with c['owner'].connect() as connection:
        result=(await connection.execute(text('SELECT d.media_type,v.configuration FROM app.documents d JOIN app.document_versions v ON v.id=d.active_version_id'))).one()
        assert result.media_type=='text/html' and result.configuration.endswith(':text/html')
    current=(await c['admin'].get(path.rsplit('/dep',1)[0])).json()['items'][0]
    assert current['status']=='capacity' and not current['entry']['active_job']


async def test_private_only_removal_is_revisioned_and_prevents_later_auto_selection(collections):
    from docweave.services.source_review import seal_candidate
    from tests.personal.test_documentation_review import revision
    c=collections
    dependency={'id':'dep','technology':'example','ecosystem':'python','docs_target':'1.2.3'}
    async with c['owner'].begin() as connection:
        await connection.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:id'),{'id':UUID(c['project']),'stack':json.dumps([dependency])})
    project=(await c['admin'].get('/api/v1/projects/'+c['project'])).json()
    candidate={'source_url':'https://docs.example.org/v1/guide.md','origin':'https://docs.example.org','path_prefix':'/v1/','attribution':'Publisher'}
    token=seal_candidate(c['data']['app'].state.github[0].encryption_key,c['user']['id'],project,dependency,candidate)
    path=f"/api/v1/projects/{c['project']}/documentation"
    accepted=await c['admin'].post(path+'/dep/review-source',json={'expected_revision':1,'candidate_token':token,'coverage':{'granularity':'exact','version':'1.2.3'}},headers=c['headers'])
    assert accepted.status_code==202,accepted.text
    removed=await c['admin'].put(path+'/dep',json={'expected_revision':2},headers=c['headers'])
    assert removed.status_code==200,removed.text
    assert removed.json()['context_revision']==3
    async with c['owner'].begin() as connection:
        public=await revision(connection,technology='example',granularity='exact',version='1.2.3')
        await connection.execute(text('SELECT app.personal_reconcile_catalog(:project,:actor,CAST(:choices AS jsonb),NULL)'),
            {'project':UUID(c['project']),'actor':UUID(c['user']['id']),'choices':json.dumps([{'dependency_id':'dep','revision_id':str(public)}])})
        assert await connection.scalar(text('SELECT count(*) FROM app.project_catalog_selections WHERE active'))==0
    current=(await c['admin'].get(path)).json()['items'][0]
    assert current['status']=='missing' and current['reason']=='documentation selection removed'
