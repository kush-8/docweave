"""One project discovers nested apps without merging their dependency versions."""
import json
import pytest
from docweave.integrations.stack import parse_stack
from tests.github.test_repository_sync import fixture_client, SHA


def app_files(folder, version):
    prefix = folder + '/' if folder else ''
    manifest = {'dependencies': {'react': '^' + version.split('.')[0]}}
    lock = {'lockfileVersion': 3, 'packages': {'': manifest,
        'node_modules/react': {'version': version}}}
    return {prefix + 'package.json': json.dumps(manifest).encode(),
            prefix + 'package-lock.json': json.dumps(lock).encode()}


def test_root_project_discovers_apps_and_keeps_their_versions_separate():
    files = {**app_files('backend', '18.3.1'), **app_files('client', '19.1.0')}
    scan = parse_stack(files)
    assert scan.complete, scan.issues
    assert {(dep.application_path, dep.name, dep.resolved_version) for dep in scan.dependencies} == {
        ('backend', 'react', '18.3.1'), ('client', 'react', '19.1.0')}
    assert parse_stack(dict(reversed(list(files.items())))).fingerprint == scan.fingerprint


def test_selected_subtree_discovers_nested_apps_without_siblings():
    files = {**app_files('apps/backend', '18.3.1'), **app_files('apps/client', '19.1.0'),
             **app_files('unrelated', '17.0.2')}
    scan = parse_stack(files, 'apps')
    assert scan.complete, scan.issues
    assert {dep.application_path for dep in scan.dependencies} == {'apps/backend', 'apps/client'}


@pytest.mark.parametrize('directory', ['node_modules', '.venv', 'vendor', 'dist', 'build', '.next'])
def test_generated_dependency_metadata_is_not_part_of_project_discovery(directory):
    files = {**app_files('client', '19.1.0'), directory + '/nested/package.json': b'{broken'}
    scan = parse_stack(files)
    assert scan.complete, scan.issues
    assert {(dep.application_path, dep.name) for dep in scan.dependencies} == {('client', 'react')}


def test_malformed_child_app_prevents_complete_repository_memory():
    scan = parse_stack({**app_files('client', '19.1.0'), 'backend/package.json': b'{broken'})
    assert not scan.complete


def test_workspace_root_and_child_manifests_are_both_discovered():
    files = {**app_files('', '18.3.1'), **app_files('client', '19.1.0')}
    manifest = json.loads(files['package.json'])
    manifest['workspaces'] = ['client']
    files['package.json'] = json.dumps(manifest).encode()
    scan = parse_stack(files)
    assert scan.complete, scan.issues
    assert {(dep.application_path, dep.resolved_version) for dep in scan.dependencies} == {('', '18.3.1'), ('client', '19.1.0')}


def test_shared_pnpm_lock_does_not_invent_a_manifest_at_the_workspace_root():
    from tests.github.test_stack import PNPM
    scan = parse_stack({'web/package.json': b'{"dependencies":{"react":"^19"}}',
        'pnpm-lock.yaml': PNPM, 'pnpm-workspace.yaml': b'packages: [web]'})
    assert scan.complete, scan.issues
    assert {(dep.application_path, dep.resolved_version) for dep in scan.dependencies} == {('web', '19.1.0')}


def test_nested_installed_version_does_not_replace_direct_declaration():
    manifest = {'dependencies': {'react': '^19', 'widget': '^1'}}
    lock = {'lockfileVersion': 3, 'packages': {'': manifest,
        'node_modules/react': {'version': '19.1.0'},
        'node_modules/widget': {'version': '1.0.0', 'dependencies': {'react': '^18'}},
        'node_modules/widget/node_modules/react': {'version': '18.3.1'}}}
    scan = parse_stack({'client/package.json': json.dumps(manifest).encode(),
        'client/package-lock.json': json.dumps(lock).encode()})
    assert scan.complete, scan.issues
    assert {(dep.name, dep.resolved_version, dep.direct) for dep in scan.dependencies} == {
        ('react', '19.1.0', True), ('widget', '1.0.0', True)}


@pytest.mark.parametrize('raw,complete', [
    (b'version=1\n[[package]]\nname="project"\nversion="1.0.0"\nsource={virtual="."}\ndependencies=[{name="fastapi"}]\n[[package]]\nname="fastapi"\nversion="1.2.3"\nsource={registry="https://pypi.org/simple"}\n', True),
    (b'not valid TOML', False),
])
def test_standalone_python_lock_is_not_lost_beside_a_javascript_app(raw, complete):
    scan = parse_stack({'uv.lock': raw, 'web/package.json': b'{}'})
    assert scan.complete is complete
    if complete:
        assert [(dep.application_path, dep.name, dep.resolved_version) for dep in scan.dependencies] == [('', 'fastapi', '1.2.3')]


@pytest.mark.anyio
async def test_live_transport_discovers_apps_at_one_commit_and_skips_generated_metadata():
    from docweave.services.repository_sync import scan_repository
    files = {**app_files('backend', '18.3.1'), **app_files('client', '19.1.0'),
             'node_modules/nested/package.json': b'{broken', 'client/source.ts': b'private source'}
    client, requests = fixture_client(files)
    result = await scan_repository(client, 'token', 42, 'main', '')
    assert result['scan'].complete, result['scan'].issues
    assert result['commit_sha'] == SHA
    assert {dep.application_path for dep in result['scan'].dependencies} == {'backend', 'client'}
    reads = {request.url.path.removeprefix('/repositories/42/contents/') for request in requests
             if '/contents/' in request.url.path}
    assert reads == {'backend/package.json', 'backend/package-lock.json', 'client/package.json', 'client/package-lock.json'}


@pytest.mark.anyio
async def test_legacy_scan_is_rebuilt_even_when_the_git_commit_is_unchanged():
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client(app_files('client', '19.1.0'))
    result = await scan_repository(client, 'token', 42, 'main', '', previous_commit=SHA,
                                   previous_fingerprint='a' * 64)
    assert result['scan'].complete and not result['unchanged']
    assert any('/trees/' in request.url.path for request in requests)
