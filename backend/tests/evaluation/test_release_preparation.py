"""Release preparation never promotes drafts or mocked captures into acceptance."""
import json
import pytest


def draft():
    return {'version': 'test-release-v1', 'human_label_review': 'pending', 'cases': [
        {'id': f'case-{i}', 'family_id': f'family-{i}', 'split': 'development' if i < 100 else 'held_out',
         'kind': 'answerable', 'query': f'How should project dependency {i} be configured?',
         'required_facts': ['Keep credentials on the backend.'], 'sources': ['https://example.test/docs'],
         'project_context': {'technology': f'library-{i}', 'docs_target': 'rolling'}, 'expected_outcome': 'answered'}
        for i in range(150)]}


def save(tmp_path, value):
    path = tmp_path / 'dataset.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def test_release_draft_preserves_100_50_split_and_pending_review(tmp_path):
    from docweave.evaluation.release import load_release_dataset
    dataset = load_release_dataset(save(tmp_path, draft()))
    assert dataset.human_label_review == 'pending'
    assert sum(case.split == 'development' for case in dataset.cases) == 100
    assert sum(case.split == 'held_out' for case in dataset.cases) == 50


def test_release_sequence_keeps_history_and_current_constraints_separate_from_labels(tmp_path):
    from docweave.evaluation.release import load_release_dataset
    value = draft()
    value['cases'][0].update(history=['What did our earlier design assume?'], constraints_after_history='Use the revised design.')
    value['cases'][0]['project_context']['constraints'] = 'Earlier design.'
    case = load_release_dataset(save(tmp_path, value)).cases[0]
    assert case.history == ['What did our earlier design assume?']
    assert case.project_context.constraints == 'Earlier design.'
    assert case.constraints_after_history == 'Use the revised design.'


@pytest.mark.parametrize('mutation', ['empty', 'oversized', 'too_many', 'change_without_history', 'nul'])
def test_release_sequence_rejects_unusable_history(tmp_path, mutation):
    from docweave.evaluation.release import load_release_dataset
    value = draft()
    case = value['cases'][0]
    case['history'] = ['A prior question']
    if mutation == 'empty': case['history'] = [' ']
    elif mutation == 'oversized': case['history'] = ['x'*4097]
    elif mutation == 'too_many': case['history'] *= 9
    elif mutation == 'change_without_history':
        case['history'] = []
        case['constraints_after_history'] = 'A new design'
    else: case['constraints_after_history'] = 'Bad\x00context'
    with pytest.raises(ValueError): load_release_dataset(save(tmp_path, value))


@pytest.mark.parametrize('revision', ['v1', 'v2', 'v3'])
def test_proposed_benchmark_loads_as_a_draft_with_both_splits(revision):
    from tests.paths import BACKEND_ROOT
    from docweave.evaluation.release import load_release_dataset
    dataset = load_release_dataset(BACKEND_ROOT / f'eval/fixtures/release-draft-{revision}.json')
    assert len(dataset.cases) == 150
    assert {case.split for case in dataset.cases} == {'development', 'held_out'}


def test_history_draft_preserves_case_families_sources_and_factual_labels():
    from tests.paths import BACKEND_ROOT
    from docweave.evaluation.release import load_release_dataset
    previous = load_release_dataset(BACKEND_ROOT/'eval/fixtures/release-draft-v2.json')
    current = load_release_dataset(BACKEND_ROOT/'eval/fixtures/release-draft-v3.json')
    before = {case.id: case for case in previous.cases}
    assert current.human_label_review == 'pending'
    assert sum(bool(case.history) for case in current.cases) == 6
    assert sum(case.constraints_after_history is not None for case in current.cases) == 2
    for split in ('development', 'held_out'):
        assert sum(bool(case.history) and case.split == split for case in current.cases) == 3
    for case in current.cases:
        assert (case.family_id, case.split, case.required_facts, case.sources) == (before[case.id].family_id, before[case.id].split, before[case.id].required_facts, before[case.id].sources)


@pytest.mark.parametrize('mutation', ['count', 'duplicate_id', 'leaked_family', 'duplicate_query', 'facts', 'url', 'outcome'])
def test_release_dataset_rejects_unusable_inputs(tmp_path, mutation):
    from docweave.evaluation.release import load_release_dataset
    value = draft()
    if mutation == 'count': value['cases'].pop()
    elif mutation == 'duplicate_id': value['cases'][1]['id'] = value['cases'][0]['id']
    elif mutation == 'leaked_family': value['cases'][100]['family_id'] = value['cases'][0]['family_id']
    elif mutation == 'duplicate_query': value['cases'][1]['query'] = '  ' + value['cases'][0]['query'].upper()
    elif mutation == 'facts': value['cases'][0]['required_facts'] = []
    elif mutation == 'url': value['cases'][0]['sources'] = ['https://user:password@example.test/docs']
    else: value['cases'][0]['expected_outcome'] = 'abstained'
    with pytest.raises(ValueError): load_release_dataset(save(tmp_path, value))


def test_human_review_packets_are_separate_reproducible_and_bound_to_captures(tmp_path):
    from docweave.evaluation.release import load_release_dataset, review_packets, ReleaseCase
    dataset = load_release_dataset(save(tmp_path, draft()))
    captures = {case.id: {'answer_kind': 'answered', 'answer': {'answer': 'An observed answer', 'citations': []}}
                for case in dataset.cases}
    packets = review_packets(dataset, captures)
    assert packets == review_packets(dataset, captures)
    ids = []
    for split in ('development', 'held_out'):
        packet = packets[split]
        assert len(packet['items']) == 30 and packet['human_review'] == 'pending'
        assert packet['semantic_quality_evidence'] is False
        assert all(item['scenario']['split'] == split and item['ratings'] is None for item in packet['items'])
        assert all(ReleaseCase.model_validate(item['scenario']) for item in packet['items'])
        ids += [item['scenario']['id'] for item in packet['items']]
    assert len(set(ids)) == 60
    captures['case-0']['answer']['answer'] = 'Changed output'
    assert review_packets(dataset, captures)['development']['captures_sha256'] != packets['development']['captures_sha256']
    captures.pop('case-0')
    with pytest.raises(ValueError, match='capture'): review_packets(dataset, captures)


def test_offline_cli_writes_pending_packets_without_dispatch(tmp_path, monkeypatch, capsys):
    from docweave.evaluation.release import main
    dataset = save(tmp_path, draft())
    captures = tmp_path / 'captures.json'
    captures.write_text(json.dumps({f'case-{i}': {'answer_kind': 'answered'} for i in range(150)}))
    output = tmp_path / 'private-reviews'
    monkeypatch.setattr('sys.argv', ['release', '--dataset', str(dataset), '--captures', str(captures), '--output', str(output)])
    main()
    for split in ('development', 'held_out'):
        packet = json.loads((output / (split + '-review.json')).read_text())
        assert len(packet['items']) == 30 and packet['human_review'] == 'pending'
    assert 'human review remains pending' in capsys.readouterr().out


@pytest.mark.parametrize('mutation', ['query', 'facts', 'context', 'history', 'context_change'])
def test_review_packets_reject_modified_loaded_labels(tmp_path, mutation):
    from docweave.evaluation.release import load_release_dataset, review_packets
    dataset = load_release_dataset(save(tmp_path, draft()))
    captures = {case.id: {} for case in dataset.cases}
    if mutation == 'query': dataset.cases[0].query = 'A changed question'
    elif mutation == 'facts': dataset.cases[0].required_facts.append('An unreviewed label')
    elif mutation == 'history': dataset.cases[0].history.append('A changed earlier question')
    elif mutation == 'context_change': dataset.cases[0].constraints_after_history = 'A different context'
    else: dataset.cases[0].project_context.docs_target = 'Different target'
    with pytest.raises(ValueError, match='changed'): review_packets(dataset, captures)


@pytest.mark.anyio
async def test_capture_preserves_retrieved_candidates_when_reranking_is_unavailable(monkeypatch):
    from uuid import UUID
    from docweave.evaluation.personal import EvaluationAnswerEngine
    from docweave.services.answer_engine import AnswerEngine
    from docweave.rag.contracts import HostedError
    identity = str(UUID(int=1))
    capture = {}
    engine = EvaluationAnswerEngine({'id': identity, 'actor_id': identity, 'project': {'id': identity,
        'context_revision': 1}, 'turn': {'id': identity}}, capture=capture, engine=None,
        read_engine=None, config={}, generation_id=UUID(int=2), authorize=None)
    engine.hits = [{'quote': f'Candidate {i}'} for i in range(12)]
    async def unavailable(*args):
        raise HostedError('provider_unavailable')
    monkeypatch.setattr(AnswerEngine, 'profile', unavailable)
    with pytest.raises(HostedError): await engine.profile(None, 'reranking')
    assert [hit['quote'] for hit in capture['retrieved_top_10']] == [f'Candidate {i}' for i in range(10)]
