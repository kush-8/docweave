import copy

import pytest
from tests.evaluation.test_release_preparation import draft, save
from docweave.evaluation.frozen import freeze_sources, prepare_support_review
from docweave.evaluation.release import load_release_dataset
from docweave.rag.parsing import parse_text

pytestmark = pytest.mark.anyio


@pytest.fixture
async def reviewed(tmp_path):
    value = draft()
    value['human_label_review'] = 'complete'
    value['cases'][1].update(kind='no_evidence', required_facts=[], sources=[], expected_outcome='abstained')
    dataset = load_release_dataset(save(tmp_path, value))
    registry = {'entries': [{'publisher_root': 'https://example.test/', 'attribution': 'Synthetic publisher',
        'pages': [{'url': 'https://example.test/docs'}]}]}
    async def fetch(selection):
        return b'# Synthetic guide\nKeep credentials on the backend.\n', 'text/markdown'
    folder = tmp_path / 'frozen'
    await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    review = prepare_support_review(dataset, folder)
    review.update(human_review='complete', reviewer='Synthetic test reviewer')
    span = review['cases']['case-0'][0]
    hit = {'source_url': span['source_url'], 'quote': span['quote'],
        'locator': {'start': span['start'], 'end': span['end']}}
    captures = {case.id: {'case_id': case.id, 'pipeline': {'retrieved_top_10': [copy.deepcopy(hit)] if case.required_facts else []}}
        for case in dataset.cases}
    batch = {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': review['sources_manifest_sha256'], 'cases': captures}
    return dataset, folder, review, batch, hit


async def test_release_recall_counts_facts_once_and_only_top_ten(reviewed):
    from docweave.evaluation.metrics import release_support_recall
    dataset, folder, review, batch, hit = reviewed
    review['cases']['case-0'].append(copy.deepcopy(review['cases']['case-0'][0]))
    distractor = {**hit, 'source_url': 'https://other.test/docs'}
    batch['cases']['case-0']['pipeline']['retrieved_top_10'] = [distractor]*10+[hit]
    result = release_support_recall(dataset, folder, review, batch)
    assert result['overall'] == {'value': 148/149, 'matched': 148, 'denominator': 149}
    assert result['by_case']['case-0'] == {'value': 0, 'matched': 0, 'denominator': 1}
    assert result['by_case']['case-1'] == {'value': None, 'matched': 0, 'denominator': 0}
    assert result['semantic_quality_evidence'] is False
    assert result['by_split']['development']['denominator'] == 99
    assert result['by_split']['held_out'] == {'value': 1, 'matched': 50, 'denominator': 50}
    batch['cases']['case-0']['pipeline']['retrieved_top_10'] = [hit, hit]
    assert release_support_recall(dataset, folder, review, batch)['overall']['matched'] == 149


@pytest.mark.parametrize('mutation', ['pending', 'dataset', 'manifest', 'missing_case', 'wrong_case', 'quote', 'offset', 'bool_offset', 'hits'])
async def test_release_recall_rejects_unreviewed_unbound_or_invalid_evidence(reviewed, mutation):
    from docweave.evaluation.metrics import release_support_recall
    dataset, folder, review, batch, _ = reviewed
    hit = batch['cases']['case-0']['pipeline']['retrieved_top_10'][0]
    if mutation == 'pending': review['human_review'] = 'pending'
    elif mutation == 'dataset': batch['dataset_sha256'] = '0'*64
    elif mutation == 'manifest': batch['sources_manifest_sha256'] = '0'*64
    elif mutation == 'missing_case': del batch['cases']['case-0']
    elif mutation == 'wrong_case': batch['cases']['case-0']['case_id'] = 'case-2'
    elif mutation == 'quote': hit['quote'] = 'Invented or stale quote'
    elif mutation == 'offset': hit['locator']['end'] += 1
    elif mutation == 'bool_offset': hit['locator']['start'] = False
    else: batch['cases']['case-0']['pipeline']['retrieved_top_10'] = None
    with pytest.raises(ValueError): release_support_recall(dataset, folder, review, batch)


async def test_release_recall_keeps_failed_execution_in_the_denominator(reviewed):
    from docweave.evaluation.metrics import release_support_recall
    dataset, folder, review, batch, _ = reviewed
    batch['cases']['case-0'] = {'case_id': 'case-0', 'outcome': 'execution_error'}
    result = release_support_recall(dataset, folder, review, batch)
    assert result['overall'] == {'value': 148/149, 'matched': 148, 'denominator': 149}


async def test_private_upload_without_url_is_a_distractor_not_frozen_support(reviewed):
    from docweave.evaluation.metrics import release_support_recall
    dataset, folder, review, batch, _ = reviewed
    batch['cases']['case-0']['pipeline']['retrieved_top_10'][0]['source_url'] = None
    result = release_support_recall(dataset, folder, review, batch)
    assert result['by_case']['case-0']['matched'] == 0
    assert result['overall']['denominator'] == 149


async def test_metric_report_binds_the_reviewed_span_choices(reviewed):
    from docweave.evaluation.metrics import release_support_recall
    dataset, folder, review, batch, _ = reviewed
    hit = batch['cases']['case-0']['pipeline']['retrieved_top_10'][0]
    sentence = 'Keep credentials on the backend.'
    start = hit['quote'].index(sentence)
    hit.update(quote=sentence, locator={'start': start, 'end': start+len(sentence)})
    before = release_support_recall(dataset, folder, review, batch)
    review['cases']['case-0'][0].update(start=start, end=start+len(sentence), quote=sentence)
    after = release_support_recall(dataset, folder, review, batch)
    assert before['overall']['matched'] == 148 and after['overall']['matched'] == 149
    for binding in ('dataset_sha256', 'sources_manifest_sha256', 'captures_sha256'):
        assert before[binding] == after[binding]
    assert before['support_review_sha256'] != after['support_review_sha256']
