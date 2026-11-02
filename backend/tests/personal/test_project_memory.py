from uuid import UUID
import pytest
from docweave.integrations.stack import parse_stack
from docweave.services.project_memory import update_memory

PROJECT = UUID(int=42)
SHA = "a" * 40

def test_stack_update_preserves_dependency_identity_and_revision_on_noop():
    scan = parse_stack({"package.json": b'{"dependencies":{"react":"19.0.0"}}'})
    first = update_memory(PROJECT, [], None, 1, scan, SHA)
    assert first["context_revision"] == 2
    assert first["last_commit_sha"] == SHA
    second = update_memory(PROJECT, first["stack"], first["stack_fingerprint"], 2, scan, "b"*40)
    assert second["context_revision"] == 2
    assert second["stack"][0]["id"] == first["stack"][0]["id"]
    assert second["last_commit_sha"] == "b"*40

def test_version_change_keeps_dependency_id_but_invalidates_context():
    a = parse_stack({"package.json": b'{"dependencies":{"react":"19.0.0"}}'})
    b = parse_stack({"package.json": b'{"dependencies":{"react":"19.1.0"}}'})
    old = update_memory(PROJECT, [], None, 1, a, SHA)
    new = update_memory(PROJECT, old["stack"], old["stack_fingerprint"], 2, b, "b"*40)
    assert new["context_revision"] == 3
    assert new["stack"][0]["id"] == old["stack"][0]["id"]


def test_incomplete_scan_cannot_overwrite_good_memory():
    bad = parse_stack({"package.json": b'{broken'})
    with pytest.raises(ValueError, match="incomplete"):
        update_memory(PROJECT, [], None, 1, bad, SHA)


def test_same_package_in_multiple_roles_has_distinct_stable_dependency_ids():
    scan=parse_stack({'package.json': b'{"dependencies":{"react":"19"},"devDependencies":{"react":"19"}}'})
    memory=update_memory(PROJECT, [], None, 1, scan, SHA)
    assert len({entry['id'] for entry in memory['stack']}) == len(memory['stack']) == 2


def test_repository_apps_keep_distinct_ids_and_stable_ids_after_version_changes():
    from tests.github.test_repository_discovery import app_files
    files = {**app_files('backend', '18.3.1'), **app_files('client', '19.1.0')}
    first = update_memory(PROJECT, [], None, 1, parse_stack(files), SHA)
    ids = {item['application_path']: item['id'] for item in first['stack']}
    assert len(set(ids.values())) == 2
    files.update(app_files('client', '19.2.0'))
    second = update_memory(PROJECT, first['stack'], first['stack_fingerprint'], 2, parse_stack(files), 'b' * 40)
    assert {item['application_path']: item['id'] for item in second['stack']} == ids
    assert second['context_revision'] == 3
    unchanged = update_memory(PROJECT, second['stack'], second['stack_fingerprint'], 3, parse_stack(files), 'c' * 40)
    assert unchanged['stack'] == second['stack'] and unchanged['context_revision'] == 3


def test_legacy_root_dependency_keeps_its_id_when_nested_apps_are_added():
    from tests.github.test_repository_discovery import app_files
    first = update_memory(PROJECT, [], None, 1, parse_stack(app_files('', '18.3.1')), SHA)
    for item in first['stack']:
        item.pop('application_path', None)
    second = update_memory(PROJECT, first['stack'], first['stack_fingerprint'], 2,
        parse_stack({**app_files('', '18.3.1'), **app_files('client', '19.1.0')}), 'b' * 40)
    root = next(item for item in second['stack'] if item['application_path'] == '')
    assert root['id'] == first['stack'][0]['id']
    assert len({item['id'] for item in second['stack']}) == 2


def test_pinned_transitive_versions_have_distinct_ids_from_direct_dependency():
    from dataclasses import replace
    from docweave.integrations.stack import Dependency, StackScan
    direct = Dependency('javascript', 'react', '^19', '19.1.0', application_path='client')
    scan = StackScan((direct, replace(direct, direct=False, resolved_version='18.3.1')), True, (), 'two-versions')
    memory = update_memory(PROJECT, [], None, 1, scan, SHA)
    assert len({item['id'] for item in memory['stack']}) == 2


def test_legacy_selected_folder_keeps_documentation_dependency_id():
    old = [{'id': str(UUID(int=99)), 'ecosystem': 'javascript', 'technology': 'react',
            'role': 'runtime', 'direct': True, 'resolved_version': '19.0.0'}]
    scan = parse_stack({'web/package.json': b'{"dependencies":{"react":"^19"}}'}, 'web')
    memory = update_memory(PROJECT, old, 'old-scan', 2, scan, SHA, application_path='web')
    assert memory['stack'][0]['id'] == str(UUID(int=99))
    assert memory['stack'][0]['application_path'] == 'web'
