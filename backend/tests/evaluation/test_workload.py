import copy
import hashlib
import json
from uuid import uuid4

import pytest
from tests.evaluation.test_release_preparation import draft, save
from tests.evaluation.test_cost_aggregation import ledger, reservation
from docweave.evaluation.frozen import freeze_sources
from docweave.evaluation.release import load_release_dataset
from docweave.rag.parsing import parse_text

pytestmark = pytest.mark.anyio


@pytest.fixture
async def workload(tmp_path):
    value = draft()
    value['cases'][0]['history'] = ['An earlier question']
    dataset = load_release_dataset(save(tmp_path, value))
    folder = tmp_path/'frozen'
    async def fetch(selection): return b'Synthetic source.', 'text/plain'
    await freeze_sources(dataset, {'entries': [{'publisher_root': 'https://example.test/', 'attribution': 'Fixture',
        'pages': [{'url': 'https://example.test/docs'}]}]}, folder, fetcher=fetch, parser=parse_text)
    configuration = {'generation_id': str(uuid4()), 'implementation_sha256': 'a'*64, 'fixture_sha256': 'b'*64,
        'transport': 'intercepted', 'guardrail_epoch': 1, 'retrieval_configuration': {'lexical': 'bm25', 'vector': 'exact'},
        'profiles': {role: {'id': str(uuid4()), 'model': 'fixture-model'} for role in ('embedding', 'query_resolution', 'reranking', 'generation')}}
    def capture(identity, query):
        turn = str(uuid4())
        return {'case_id': identity, 'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
            'append_http_status': 202, 'http_status': 200, 'outcome': 'turn_result', 'turn_id': turn,
            'released_turn': {'id': turn, 'message': query, 'status': 'completed'},
            'pipeline': {'implementation': {'sha256': 'a'*64}, 'generation_id': configuration['generation_id'],
                'policy_epoch': 1, 'retrieval_configuration': configuration['retrieval_configuration'], 'stages': [], 'ledger': ledger()}}
    cases = {}
    for case in dataset.cases:
        row = capture(case.id, case.query)
        row['history'] = [capture(case.id+':history:'+str(index), query) for index, query in enumerate(case.history)]
        cases[case.id] = row
    batch = {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(), 'source_blocked_answer_cases': [],
        'configuration': configuration, 'cases': cases}
    return dataset, folder, batch


async def test_every_planned_turn_is_accounted_without_inventing_quality(workload):
    from docweave.evaluation.workload import summarize_offline_workload
    dataset, folder, batch = workload
    result = summarize_offline_workload(dataset, folder, batch)
    assert result['planned_turns'] == result['captured_turns'] == 151
    assert result['accepted_turns'] == 151
    assert result['outcomes'] == {'turn_result': 151}
    assert result['release_ready'] is False and result['semantic_quality_evidence'] is False
    assert result['costs']['unique_reservations'] == 0


@pytest.mark.parametrize('mutation', ['case', 'history', 'query', 'manifest', 'turn', 'ledger', 'configuration', 'implementation', 'stage'])
async def test_incomplete_or_unbound_workload_is_not_reported_complete(workload, mutation):
    from docweave.evaluation.workload import summarize_offline_workload
    dataset, folder, batch = workload
    row = batch['cases']['case-0']
    if mutation == 'case': del batch['cases']['case-1']
    elif mutation == 'history': row['history'] = []
    elif mutation == 'query': row['query_sha256'] = '0'*64
    elif mutation == 'manifest': batch['sources_manifest_sha256'] = '0'*64
    elif mutation == 'turn': row['turn_id'] = str(uuid4())
    elif mutation == 'ledger': del row['pipeline']['ledger']
    elif mutation == 'configuration': batch['configuration']['OPENAI_API_KEY'] = 'Must not be captured'
    elif mutation == 'implementation': row['pipeline']['implementation']['sha256'] = '0'*64
    else: row['pipeline']['stages'] = [{'stage': 'generation', 'profile_id': str(uuid4()), 'model': 'fixture-model'}]
    with pytest.raises(ValueError): summarize_offline_workload(dataset, folder, batch)


async def test_denials_errors_and_reused_claims_remain_explicit(workload):
    from docweave.evaluation.workload import summarize_offline_workload
    dataset, folder, batch = workload
    batch['cases']['case-2'] = {'case_id': 'case-2', 'query_sha256': hashlib.sha256(dataset.cases[2].query.encode()).hexdigest(),
        'append_http_status': 404, 'http_status': 404, 'outcome': 'http_denied', 'history': []}
    row = reservation()
    row['profile_id'] = batch['configuration']['profiles']['generation']['id']
    evidence = ledger(row)
    failed = batch['cases']['case-0']
    failed['outcome'] = 'execution_error'
    failed['pipeline']['ledger'] = evidence
    failed['ledger'] = copy.deepcopy(evidence)
    result = summarize_offline_workload(dataset, folder, batch)
    assert result['outcomes'] == {'execution_error': 1, 'turn_result': 149, 'http_denied': 1}
    assert result['costs']['unique_reservations'] == 1
    assert result['costs']['unsettled_usd'] == row['maximum_usd']
    assert result['release_ready'] is False
