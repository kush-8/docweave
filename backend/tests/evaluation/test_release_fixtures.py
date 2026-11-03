from types import SimpleNamespace
from pathlib import Path
import os
import json
from uuid import UUID

import pytest
from sqlalchemy import make_url, text
from tests.database.test_database import databases, test_urls  # noqa: F401
from tests.github.test_github import github_login  # noqa: F401
from tests.support.personal import collections  # noqa: F401
from tests.paths import BACKEND_ROOT
from docweave.core.identity import Actor
from docweave.core.errors import DomainError
from docweave.core.guardrails import assess_text
from docweave.evaluation.frozen import freeze_sources, load_frozen_sources
from docweave.evaluation.release import load_release_dataset
from docweave.rag.parsing import parse_text
from docweave.rag.retrieval import retrieve_channels
from docweave.storage.artifacts import ArtifactStore

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize('url', ['postgresql+asyncpg://docweave_migrator@127.0.0.1:55432/docweave',
    'postgresql+asyncpg://docweave_migrator@other:55433/docweave_test'])
async def test_offline_release_setup_refuses_development_or_remote_targets(url):
    from tests.support.release import materialize_release_cases
    connection = SimpleNamespace(engine=SimpleNamespace(url=make_url(url)))
    with pytest.raises(ValueError, match='isolated test database'):
        await materialize_release_cases(connection, None, None, None, None, None)


@pytest.mark.parametrize('source_blocked', [False, True])
async def test_every_release_case_has_real_source_version_or_access_state(collections, tmp_path, source_blocked, record_testsuite_property):
    from tests.support.release import materialize_release_cases
    from docweave.services.retention import mark
    c = collections
    dataset = load_release_dataset(BACKEND_ROOT / 'eval/fixtures/release-draft-v3.json')
    if os.environ.get('DOCWEAVE_RELEASE_FROZEN_SOURCES'):
        folder = Path(os.environ['DOCWEAVE_RELEASE_FROZEN_SOURCES'])
    else:
        urls = {url for case in dataset.cases for url in case.sources}
        registry = {'entries': [{'publisher_root': url, 'attribution': 'Synthetic offline fixture', 'pages': [{'url': url}]} for url in urls]}
        async def fetch(selection):
            if source_blocked and 'sqlalchemy/' in selection['source_url']:
                return b'Synthetic blocked example: postgresql://fixture-user:fixture-secret@database.invalid/db\r\n', 'text/plain'
            return b'# Synthetic offline guide\r\nConfiguration is documented here.\r\n', 'text/markdown'
        folder = tmp_path / 'frozen'
        await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    parsed = load_frozen_sources(dataset, folder)
    store = ArtifactStore(tmp_path / 'artifacts')
    async with c['owner'].begin() as connection:
        before = await connection.scalar(text('SELECT count(*) FROM app.cost_reservations'))
        setups = await materialize_release_cases(connection, dataset, folder, UUID(c['user']['id']), UUID(c['recipient']['id']), store)
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == before
        assert await connection.scalar(text('SELECT count(*) FROM app.provider_profiles WHERE enabled')) == 0
    c['data']['app'].state.ingestion_store = store
    mark(c['runtime'], True, artifact_root=store.root)
    revoked = set()
    async def repository(token, identity):
        if identity in revoked:
            raise DomainError('forbidden')
        return {'id': identity, 'name': 'offline-repository', 'default_branch': 'main'}
    c['data']['app'].state.github[2].repository = repository
    manifest = json.loads((folder / 'manifest.json').read_text())
    async with c['owner'].connect() as connection:
        catalog_hashes = (await connection.execute(text('SELECT source_url,source_hash FROM app.public_catalog_revisions'))).all()
    for source_url, raw_hash in catalog_hashes:
        if source_url in manifest['sources']:
            assert raw_hash == manifest['sources'][source_url]['raw_sha256']
    assert set(setups['cases']) == {case.id for case in dataset.cases}
    assert setups['semantic_quality_evidence'] is False and setups['provider_calls'] == 0
    for case in dataset.cases:
        state = setups['cases'][case.id]
        if case.project_context.constraints:
            async with c['owner'].connect() as connection:
                assert await connection.scalar(text('SELECT constraints FROM app.projects WHERE id=:id'), {'id': UUID(state['project_id'])}) == case.project_context.constraints
        response = await c['admin'].get('/api/v1/conversations/'+state['conversation_id'])
        if case.kind == 'denied':
            assert response.status_code == 404
            assert (await c['guest'].get('/api/v1/conversations/'+state['conversation_id'])).status_code == 200
            assert (await c['admin'].get('/api/v1/turns/'+state['retained_turn_id'])).status_code == 404
            retained = await c['guest'].get('/api/v1/turns/'+state['retained_turn_id'])
            assert retained.status_code == 200
            assert retained.json()['status'] == 'completed' and retained.json()['answer'] == 'Synthetic retained private answer'
            citation = '/api/v1/turns/'+state['retained_turn_id']+'/citations/offline-private'
            assert (await c['admin'].get(citation)).status_code == 404
            assert (await c['guest'].get(citation)).json()['excerpt'] == 'Synthetic other-owner private deployment instructions.'
            if case.id == 'policy-denied-evidence':
                assert state['repository_id'] != 42
                revoked.add(state['repository_id'])
                assert (await c['guest'].get('/api/v1/turns/'+state['retained_turn_id'])).status_code == 403
                assert (await c['guest'].get(citation)).status_code == 403
        else:
            assert response.status_code == 200, (case.id, response.text)
        if case.kind == 'answerable':
            result = await retrieve_channels(Actor(UUID(c['user']['id'])), UUID(state['project_id']), case.query,
                collection_ids=[UUID(identity) for identity in state['collection_ids']],
                generation_id=UUID(setups['generation_id']), query_vector=[1.0]+[0.0]*767, engine=c['runtime'])
            assert bool(result['vector']) is not bool(state['source_guardrail_blocked']), case.id
            for hit in result['vector']:
                assert hit['source_url'] in case.sources
                assert parsed[hit['source_url']]['text'][hit['locator']['start']:hit['locator']['end']] == hit['quote']
        elif case.kind == 'version':
            assert state['installed_target'] in ('16.7.0', '2.1')
            assert state['source_target'] != state['installed_target'] and state['fallback_accepted'] is False
            async with c['owner'].begin() as connection:
                await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true),set_config('docweave.personal_project_id',:project,true)"),
                    {'actor': c['user']['id'], 'project': state['project_id']})
                assert not await connection.scalar(text('SELECT app.personal_collection_allowed(:collection)'),
                    {'collection': UUID(state['collection_ids'][0])})
        elif case.kind == 'no_evidence':
            assert state['catalog_revision_ids'] == []
            async with c['owner'].connect() as connection:
                assert await connection.scalar(text('SELECT count(*) FROM app.documents WHERE collection_id=:id'), {'id': UUID(state['default_collection_id'])}) == 0
        elif case.kind == 'guardrail':
            assert assess_text(case.query).injection_flagged
    blocked = [case.id for case in dataset.cases if case.kind == 'answerable' and setups['cases'][case.id]['source_guardrail_blocked']]
    assert setups['source_blocked_answer_cases'] == blocked
    assert setups['all_answerable_cases_have_eligible_sources'] is (not blocked)
    if not os.environ.get('DOCWEAVE_RELEASE_FROZEN_SOURCES'):
        assert len(blocked) == (4 if source_blocked else 0)
    record_testsuite_property('dataset_sha256', dataset._sha256)
    record_testsuite_property('materialized_case_count', len(setups['cases']))
    record_testsuite_property('source_blocked_answer_cases', json.dumps(blocked))
    record_testsuite_property('semantic_quality_evidence', False)


async def test_offline_setup_requires_active_transaction_and_migration_role(databases):
    from tests.support.release import materialize_release_cases
    owner, runtime = databases
    async with owner.connect() as connection:
        with pytest.raises(ValueError, match='transaction'):
            await materialize_release_cases(connection, None, None, None, None, None)
    async with runtime.begin() as connection:
        with pytest.raises(ValueError, match='migration role'):
            await materialize_release_cases(connection, None, None, None, None, None)
