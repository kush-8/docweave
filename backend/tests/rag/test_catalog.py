from docweave.integrations.stack import Dependency
from docweave.services.catalog import match_documentation
from docweave.services.turn_readiness import decide_turn_readiness


def entry(**changes):
    return {'technology': 'fast-api', 'ecosystem': 'python', 'docs_target': '1.2.3',
            'coverage': {'granularity': 'exact', 'version': '1.2.3'}, 'revision_id': 'r1',
            'generation_id': 'g1', 'indexed_generation_id': 'g1', 'eligible': True,
            'source_approved': True, 'status': 'indexed', 'active_job': True, **changes}


def dependency(name='Fast_API', version='1.2.3', ecosystem='python'):
    return Dependency(ecosystem, name, documentation_target=version)


def test_exact_coverage_and_explicit_aliases():
    assert match_documentation(dependency(), [entry()], 'g1')['status'] == 'ready'
    assert match_documentation(dependency('fastapi'), [entry()], 'g1')['status'] == 'missing'
    assert match_documentation(dependency('fastapi'), [entry(package_aliases=['fastapi'])], 'g1')['status'] == 'ready'
    assert match_documentation(dependency('@org/name', ecosystem='javascript'), [entry(technology='@org/name', ecosystem='javascript')], 'g1')['status'] == 'ready'
    assert match_documentation(dependency('@org/name', ecosystem='javascript'), [entry(technology='org-name', ecosystem='javascript')], 'g1')['status'] == 'missing'


def test_versions_and_explicit_project_fallback_acceptance():
    assert match_documentation(dependency(version='2.0.0'), [entry()], 'g1')['status'] == 'missing'
    for granularity, version in [('major', '1'), ('minor', '1.2')]:
        candidate = entry(coverage={'granularity': granularity, 'version': version})
        assert match_documentation(dependency(), [candidate], 'g1')['status'] == 'pending_review'
        assert match_documentation(dependency(), [candidate], 'g1', accepted_fallback_revision_ids={'r1'})['status'] == 'ready'
    assert match_documentation(dependency(version=None), [entry()], 'g1')['status'] == 'pending_review'
    candidate = entry(coverage={'granularity': 'major', 'version': '1'})
    assert match_documentation(dependency(version='10.2.0'), [candidate], 'g1')['status'] == 'missing'


def test_current_publication_and_eligibility_are_required():
    assert match_documentation(dependency(), [entry(indexed_generation_id='old')], 'g1')['status'] == 'waiting_for_sources'
    assert match_documentation(dependency(), [entry(status='parsed')], 'g1')['status'] == 'waiting_for_sources'
    assert match_documentation(dependency(), [entry(eligible=False)], 'g1')['status'] == 'missing'
    assert match_documentation(dependency(), [entry(source_approved=False)], 'g1')['status'] == 'pending_review'
    assert match_documentation(dependency(), [entry(generation_id='old')], 'g1')['status'] == 'waiting_for_sources'


def test_exact_ready_match_beats_fallback_and_incomplete():
    fallback = entry(revision_id='fallback', coverage={'granularity': 'major', 'version': '1'})
    for candidates in ([fallback, entry()], [entry(), fallback]):
        result = match_documentation(dependency(), candidates, 'g1')
        assert result['status'] == 'ready'
        assert result['entry']['revision_id'] == 'r1'


def test_only_known_required_dependencies_with_active_jobs_wait():
    states = {'react': {'status': 'waiting_for_sources', 'active_job': True}, 'python': {'status': 'ready'}}
    assert decide_turn_readiness([], states)['status'] == 'ready'
    assert decide_turn_readiness(['python'], states)['status'] == 'ready'
    assert decide_turn_readiness(['react'], states)['status'] == 'waiting_for_sources'
    assert decide_turn_readiness(None, states)['status'] == 'clarify'
    assert decide_turn_readiness(['unknown'], states)['status'] == 'clarify'
    assert decide_turn_readiness(['react'], {'react': {'status': 'waiting_for_sources'}})['status'] == 'abstain'
    assert decide_turn_readiness(['react'], {'react': {'status': 'missing', 'active_job': True}})['status'] == 'abstain'
    assert decide_turn_readiness(['react'], {'react': {'status': 'pending_review'}})['status'] == 'pending_review'


def test_failed_and_unstarted_catalog_work_is_not_reported_as_loading():
    assert match_documentation(dependency(), [entry(status='failed')], 'g1')['status'] == 'failed'
    assert match_documentation(dependency(), [entry(status='parsed', active_job=False)], 'g1')['status'] == 'missing'
    assert match_documentation(dependency(), [entry(status='parsed', active_job=True)], 'g1')['status'] == 'waiting_for_sources'
