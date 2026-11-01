import pytest
from cryptography.fernet import Fernet


def context():
    return {'id': 'p', 'context_revision': 2, 'stack': [{'id': 'd', 'technology': 'example', 'ecosystem': 'python', 'docs_target': '1.2.3'}]}


def test_review_token_is_expiring_and_bound_to_owner_project_dependency_and_context():
    from docweave.services.source_review import seal_candidate, open_candidate
    key = Fernet.generate_key()
    project = context()
    candidate = {'source_url': 'https://docs.example.org/v1/guide.md', 'origin': 'https://docs.example.org', 'path_prefix': '/v1/', 'attribution': 'Publisher', 'registry_url': 'https://pypi.org/pypi/example/1.2.3/json'}
    token = seal_candidate(key, 'owner', project, project['stack'][0], candidate)
    assert open_candidate(key, token, 'owner', project, 'd') == candidate
    with pytest.raises(ValueError):
        open_candidate(key, token, 'other', project, 'd')
    with pytest.raises(ValueError):
        open_candidate(key, token, 'owner', {**project, 'context_revision': 3}, 'd')
    with pytest.raises(ValueError):
        open_candidate(key, token + 'bad', 'owner', project, 'd')


def test_private_source_review_requires_actual_matching_coverage_and_explicit_fallback():
    from docweave.services.source_review import review_values
    dependency = context()['stack'][0]
    candidate = {'source_url': 'https://docs.example.org/v1/guide.md', 'origin': 'https://docs.example.org', 'path_prefix': '/v1/', 'attribution': 'Publisher'}
    with pytest.raises(ValueError):
        review_values(dependency, candidate, {'granularity': 'major', 'version': '1'}, False)
    values = review_values(dependency, candidate, {'granularity': 'major', 'version': '1'}, True)
    assert values['docs_target'] == '1.2.3'
    assert 'source_hash' not in values and 'catalog_revision_id' not in values
    with pytest.raises(ValueError):
        review_values(dependency, candidate, {'granularity': 'exact', 'version': '2.0.0'}, True)
