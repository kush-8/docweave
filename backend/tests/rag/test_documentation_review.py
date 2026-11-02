from docweave.services.catalog import match_documentation
from docweave.services.catalog import documentation_coverage
from docweave.services.personal_worker import prepare_answer
from tests.rag.test_catalog import entry, dependency
import pytest


def test_revoked_source_is_not_loading_and_unknown_source_needs_operator_review():
    assert match_documentation(dependency(), [entry(status='blocked_policy')], 'g1')['status'] == 'pending_review'
    result = match_documentation(dependency(), [entry(source_approved=False)], 'g1')
    assert result['reason'] == 'source approval required'


def test_exact_coverage_is_preferred_over_accepted_fallback_even_when_not_ready():
    fallback = entry(revision_id='fallback', coverage={'granularity': 'major', 'version': '1'})
    exact = entry(status='failed', active_job=False)
    result = match_documentation(dependency(), [fallback, exact], 'g1', accepted_fallback_revision_ids={'fallback'})
    assert result['entry']['revision_id'] == 'r1'
    assert result['status'] == 'failed'


@pytest.mark.anyio
@pytest.mark.parametrize(('status', 'phrase'), [('pending_review', 'approval'), ('capacity', 'capacity'), ('missing', 'missing'), ('consent_required', 'permission')])
async def test_unavailable_documentation_has_distinct_actionable_answers(status, phrase):
    result = await prepare_answer({'message': 'Help with React'}, {'stack': [{'id': 'react', 'technology': 'React'}]}, {'react': {'status': status}})
    assert result['status'] == 'completed'
    assert phrase in result['answer'].lower()
    assert not result['citations']


def test_coverage_reuses_only_the_target_explicitly_accepted_by_this_project():
    candidate = entry(coverage={'granularity': 'major', 'version': '1'})
    project = {'stack': [{'id': 'dep', 'technology': 'Fast_API', 'ecosystem': 'python', 'docs_target': '1.2.3'}],
        'catalog_selections': [{'dependency_id': 'dep', 'revision_id': 'r1', 'fallback_accepted': True, 'accepted_docs_target': '1.2.3'}]}
    assert documentation_coverage(project, [candidate], 'g1')[0]['status'] == 'ready'
    project['stack'][0]['docs_target'] = '1.3.0'
    assert documentation_coverage(project, [candidate], 'g1')[0]['status'] == 'pending_review'


def test_repository_app_folders_keep_independent_documentation_acceptance():
    candidate = entry(technology='react', ecosystem='javascript', docs_target='19.0.0',
        coverage={'granularity': 'major', 'version': '19'})
    project = {'stack': [
        {'id': 'backend-react', 'technology': 'react', 'ecosystem': 'javascript', 'docs_target': '19.1.0', 'application_path': 'backend'},
        {'id': 'client-react', 'technology': 'react', 'ecosystem': 'javascript', 'docs_target': '19.2.0', 'application_path': 'client'}],
        'catalog_selections': [{'dependency_id': 'client-react', 'revision_id': 'r1',
            'fallback_accepted': True, 'accepted_docs_target': '19.2.0'}]}
    result = documentation_coverage(project, [candidate], 'g1')
    assert [(item['application_path'], item['status']) for item in result] == [
        ('backend', 'pending_review'), ('client', 'ready')]
