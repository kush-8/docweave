"""Draft sequences use actual HTTP/jobs and admitted stages with fake provider transport."""
import json
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from tests.database.test_database import databases, test_urls  # noqa: F401
from tests.github.test_github import github_login  # noqa: F401
from tests.support.personal import collections  # noqa: F401
from tests.support.release import materialize_release_cases
from tests.paths import BACKEND_ROOT
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.evaluation.execution import execute_http_turn
from docweave.evaluation.personal import capture_personal_job
from docweave.evaluation.costs import capture_job_costs
from docweave.evaluation.fingerprint import source_fingerprint
from docweave.evaluation.release import load_release_dataset
from docweave.evaluation.frozen import freeze_sources
from docweave.rag.parsing import parse_text
from docweave.services.retention import mark
from docweave.storage.artifacts import ArtifactStore

pytestmark = pytest.mark.anyio


@pytest.fixture
async def offline_execution(collections, tmp_path, monkeypatch):
    c = collections
    dataset = load_release_dataset(BACKEND_ROOT/'eval/fixtures/release-draft-v3.json')
    if os.environ.get('DOCWEAVE_RELEASE_FROZEN_SOURCES'):
        folder = Path(os.environ['DOCWEAVE_RELEASE_FROZEN_SOURCES'])
    else:
        urls = {url for case in dataset.cases for url in case.sources}
        registry = {'entries': [{'publisher_root': url, 'attribution': 'Synthetic sequence fixture', 'pages': [{'url': url}]} for url in urls]}
        async def fetch(selection):
            return b'# Synthetic sequence\nFixture documentation supports this structural response.\n', 'text/markdown'
        folder = tmp_path/'frozen'
        await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    actor = UUID(c['user']['id'])
    store = ArtifactStore(tmp_path/'artifacts')
    async with c['owner'].begin() as connection:
        setups = await materialize_release_cases(connection, dataset, folder, actor, UUID(c['recipient']['id']), store)
        generation = UUID(setups['generation_id'])
        generation_row = (await connection.execute(text('SELECT model,backend,processor_ids FROM app.index_generations WHERE id=:id'), {'id': generation})).mappings().one()
        assert generation_row['model'] == 'text-embedding-3-small'
    c['data']['app'].state.ingestion_store = store
    embedding_processor = generation_row['processor_ids'][0]
    profiles = {}
    async with c['owner'].begin() as connection:
        await connection.execute(text("INSERT INTO app.processors(id,provider,backend,roles,enabled) VALUES('test:sequence:llm','groq','fixture','[\"query_resolution\",\"reranking\",\"generation\"]',true) ON CONFLICT(id) DO UPDATE SET enabled=true"))
        for role in ('embedding', 'query_resolution', 'reranking', 'generation'):
            profiles[role] = uuid4()
            processors = [embedding_processor] if role == 'embedding' else ['test:sequence:llm']
            if role == 'generation': processors = [embedding_processor, 'test:sequence:llm']
            await connection.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,
                input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,max_attempts,
                enabled,capabilities_verified,account_verified,pricing_verified)
                VALUES(:id,:provider,:model,:backend,:role,CAST(:processors AS jsonb),0,0,0,131072,4096,1,true,true,true,true)"""),
                {'id': profiles[role], 'provider': 'openai' if role == 'embedding' else 'groq',
                 'model': 'text-embedding-3-small' if role == 'embedding' else 'openai/gpt-oss-120b' if role == 'generation' else 'openai/gpt-oss-20b',
                 'backend': generation_row['backend'] if role == 'embedding' else 'fixture',
                 'role': role, 'processors': json.dumps(processors)})
    requests = []
    async def transport(embedding, encoded, key, **kwargs):
        payload = json.loads(encoded)
        requests.append(payload)
        if embedding:
            return {'model': 'text-embedding-3-small', 'data': [{'index': 0, 'embedding': [1.0]+[0.0]*767}], 'usage': {'prompt_tokens': 10}}
        name = payload['response_format']['json_schema']['name']
        envelope = json.loads(payload['messages'][1]['content'])
        if name == 'dependency_resolution':
            result = {'uncertain': False, 'dependency_ids': [entry['id'] for entry in envelope['project_context']['stack']]}
        elif name == 'ranking':
            result = {'ordered_chunk_ids': [hit['chunk_id'] for hit in envelope['evidence']]}
        else:
            hit = envelope['evidence'][0]
            result = {'kind': 'answered', 'blocks': [{'kind': 'documentation', 'text': hit['quote'], 'chunk_ids': [hit['chunk_id']]}]}
        return {'model': payload['model'], 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post', transport)
    monkeypatch.setattr('docweave.integrations.openai.provider_post', transport)
    settings, _, github = c['data']['app'].state.github
    config = {'EMBEDDING_PROVIDER': 'openai', 'EMBEDDING_PROFILE_ID': str(profiles['embedding']),
        'QUERY_PROFILE_ID': str(profiles['query_resolution']), 'RERANK_PROFILE_ID': str(profiles['reranking']),
        'OPENAI_API_KEY': 'fixture-key', 'GROQ_API_KEY': 'fixture-key'}
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    captures = []
    async def execute(turn):
        async with c['owner'].connect() as connection:
            job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:id AS uuid)'), {'id': turn})
        capture = await capture_personal_job(job, engine=worker, read_engine=c['runtime'], settings=settings,
            client=github, config=config, generation_id=generation)
        capture['ledger'] = await capture_job_costs(job, engine=c['owner'])
        captures.append(capture)
        return capture
    async def sequence(case, project, chat):
        results = []
        for index, question in enumerate([*case.history, case.query]):
            if index == len(case.history) and case.constraints_after_history is not None:
                async with c['owner'].begin() as connection:
                    await connection.execute(text("UPDATE app.projects SET constraints=:constraints,context_revision=context_revision+1 WHERE id=:project AND constraints IS DISTINCT FROM :constraints"),
                        {'project': project, 'constraints': case.constraints_after_history})
            identity = case.id if index == len(case.history) else case.id+':history:'+str(index)
            result = await execute_http_turn(SimpleNamespace(id=identity, query=question), client=c['admin'],
                headers=c['headers'], conversation_id=chat, execute_job=execute)
            results.append(result)
        return results
    async def prepare_chat(case):
        # These component fixtures model healthy maintenance; worker scheduling has separate process tests.
        mark(c['runtime'], True)
        mark(c['runtime'], True, artifact_root=store.root)
        project = UUID(setups['cases'][case.id]['project_id'])
        if case.kind == 'denied':
            return project, setups['cases'][case.id]['conversation_id']
        async with c['owner'].begin() as connection:
            for processor in (embedding_processor, 'test:sequence:llm'):
                await connection.execute(text('INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:project,:processor,:actor)'), {'project': project, 'processor': processor, 'actor': actor})
        accepted = await c['admin'].post(f'/api/v1/projects/{project}/conversations', json={'answer_profile_id': str(profiles['generation'])}, headers=c['headers'])
        assert accepted.status_code == 202, accepted.text
        chat = accepted.json()['id']
        async with c['owner'].begin() as connection:
            await connection.execute(text("UPDATE app.personal_jobs SET status='completed' WHERE conversation_id=CAST(:id AS uuid)"), {'id': chat})
            await connection.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"), {'id': chat})
        return project, chat
    async with c['owner'].connect() as connection:
        profile_snapshot = {}
        for role, identity in profiles.items():
            model = await connection.scalar(text('SELECT model FROM app.provider_profiles WHERE id=:id'), {'id': identity})
            profile_snapshot[role] = {'id': str(identity), 'model': model}
        epoch = await connection.scalar(text('SELECT epoch FROM app.guardrail_policy'))
    configuration = {'generation_id': str(generation), 'transport': 'intercepted', 'guardrail_epoch': epoch,
        'retrieval_configuration': {'lexical': 'bm25', 'vector': 'exact'}, 'profiles': profile_snapshot,
        'implementation_sha256': source_fingerprint(paths=[*(BACKEND_ROOT/'src/docweave').rglob('*.py'),
            *(BACKEND_ROOT/'alembic/versions').glob('*.py'), BACKEND_ROOT/'uv.lock'])['sha256'],
        'fixture_sha256': source_fingerprint(paths=[*(BACKEND_ROOT/'tests').rglob('*.py')])['sha256']}
    try:
        yield {'c': c, 'dataset': dataset, 'folder': folder, 'setups': setups, 'configuration': configuration,
            'requests': requests, 'captures': captures, 'prepare_chat': prepare_chat, 'sequence': sequence}
    finally:
        await worker.dispose()


async def test_draft_sequences_use_persisted_history_latest_context_and_original_intents(offline_execution):
    execution = offline_execution
    dataset, captures, requests = execution['dataset'], execution['captures'], execution['requests']
    sequence = execution['sequence']
    for case in [case for case in dataset.cases if case.history]:
        project, chat = await execution['prepare_chat'](case)
        capture_count, request_count = len(captures), len(requests)
        first = await sequence(case, project, chat)
        assert all(item['released_turn']['status'] == 'completed' for item in first)
        assert len(captures)-capture_count == 2 and len(requests)-request_count == 8
        assert all(capture['stages'][-1]['model'] == 'openai/gpt-oss-120b' for capture in captures[capture_count:])
        resolutions = [json.loads(payload['messages'][1]['content']) for payload in requests[request_count:] if 'input' not in payload and payload['response_format']['json_schema']['name'] == 'dependency_resolution']
        assert resolutions[0]['conversation_context'] == []
        assert resolutions[0]['project_context']['constraints'] == case.project_context.constraints
        changed = case.constraints_after_history is not None
        assert resolutions[1]['project_context']['constraints'] == (case.constraints_after_history if changed else case.project_context.constraints)
        assert resolutions[1]['project_context']['context_revision'] == (2 if changed else 1)
        assert resolutions[1]['conversation_context'][0]['message'] == case.history[0]
        assert resolutions[1]['conversation_context'][0]['answer'] == first[0]['released_turn']['answer']
        assert first[0]['released_turn']['context_revision'] == 1 and first[1]['released_turn']['context_revision'] == (2 if changed else 1)
        assert 'required_facts' not in json.dumps(requests[request_count:]) and 'expected_outcome' not in json.dumps(requests[request_count:])
        assert case.id not in json.dumps(requests[request_count:])
        second = await sequence(case, project, chat)
        assert [item['released_turn']['id'] for item in first] == [item['released_turn']['id'] for item in second]
        assert len(captures)-capture_count == 2 and len(requests)-request_count == 8
    assert len(captures) == 12 and len(requests) == 48
    assert len({row['id'] for capture in captures for row in capture['ledger']['reservations']}) == 48
    assert all(capture['ledger']['retained_usd'] == 0 and capture['semantic_quality_evidence'] is False for capture in captures)


async def test_complete_offline_workload_freezes_all_turns_and_replays_without_dispatch(offline_execution, record_testsuite_property):
    from docweave.evaluation.reports import write_report
    from docweave.evaluation.workload import summarize_offline_workload
    execution = offline_execution
    dataset, setups = execution['dataset'], execution['setups']
    output = os.environ.get('DOCWEAVE_RELEASE_OFFLINE_OUTPUT')
    if output:
        output = Path(output).resolve()
        if not output.is_relative_to((BACKEND_ROOT.parent/'backups').resolve()):
            raise ValueError('Offline captures must stay in private backups')
        output.mkdir(parents=True, exist_ok=False)
        write_report(output/'configuration.json', execution['configuration'])
    batch = {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': setups['sources_manifest_sha256'],
        'configuration': execution['configuration'], 'source_blocked_answer_cases': setups['source_blocked_answer_cases'], 'cases': {}}
    conversations = {}
    for case in dataset.cases:
        project, chat = await execution['prepare_chat'](case)
        conversations[case.id] = project, chat
        records = await execution['sequence'](case, project, chat)
        final = records[-1]
        final['history'] = records[:-1]
        batch['cases'][case.id] = final
        if case.kind == 'denied':
            assert final['append_http_status'] == 404 and final['outcome'] == 'http_denied', case.id
        else:
            assert all(row['outcome'] == 'turn_result' and row['http_status'] == 200 for row in records), (case.id, records)
        if output:
            write_report(output/'captures.json', batch)
    summary = summarize_offline_workload(dataset, execution['folder'], batch)
    assert summary['planned_turns'] == summary['captured_turns'] == 156
    assert summary['accepted_turns'] == 156-sum(case.kind == 'denied' for case in dataset.cases)
    assert summary['costs']['retained_usd'] == summary['costs']['unsettled_usd'] == 0
    assert summary['costs']['unique_reservations'] == len(execution['requests'])
    assert all(row['status'] == 'metered' for row in summary['costs']['reservations'])
    request_count = len(execution['requests'])
    for case in dataset.cases:
        replay = await execution['sequence'](case, *conversations[case.id])
        original = batch['cases'][case.id]
        assert [row.get('turn_id') for row in replay] == [row.get('turn_id') for row in [*original['history'], original]]
    assert len(execution['requests']) == request_count
    async with execution['c']['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == summary['costs']['unique_reservations']
    payloads = json.dumps(execution['requests'])
    assert 'required_facts' not in payloads and 'expected_outcome' not in payloads
    assert all(case.id not in payloads for case in dataset.cases)
    if output:
        write_report(output/'requests.json', execution['requests'])
        write_report(output/'provisioning.json', setups)
        write_report(output/'summary.json', {**summary, 'replay_added_requests': 0})
    for key in ('dataset_sha256', 'configuration_sha256', 'captures_sha256', 'captured_turns', 'source_blocked_answer_cases'):
        record_testsuite_property(key, str(summary[key]))
