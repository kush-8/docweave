from docweave.integrations.stack import parse_stack
import json
import pytest


PNPM = b"""lockfileVersion: '9.0'
importers:
  web:
    dependencies:
      react: {specifier: ^19, version: 19.1.0}
  sibling:
    dependencies:
      react: {specifier: ^18, version: 18.3.1}
packages:
  react@19.1.0: {resolution: {integrity: sha512-test}}
  react@18.3.1: {resolution: {integrity: sha512-test}}
snapshots:
  react@19.1.0: {}
  react@18.3.1: {}
"""


def test_pnpm_ancestor_importer_does_not_mix_sibling_versions():
    files = {'web/package.json': b'{"dependencies":{"react":"^19"}}', 'pnpm-lock.yaml': PNPM,
        'pnpm-workspace.yaml': b'packages: [web, sibling]'}
    scan = parse_stack(files, 'web')
    assert scan.complete, scan.issues
    assert [(d.name, d.resolved_version, d.declared_constraint) for d in scan.dependencies] == [('react', '19.1.0', '^19')]


@pytest.mark.parametrize('lock', [
    PNPM.replace(b"'9.0'", b"'6.0'"),
    PNPM.replace(b'specifier: ^19', b'specifier: ^18'),
    PNPM.replace(b'  web:', b'  missing:'),
    PNPM + b'importers: {}\n',
    b"lockfileVersion: '9.0'\nimporters: &alias {web: *alias}\n",
    b"!!python/object/apply:os.system ['echo private-marker']",
    PNPM.replace(b'version: 19.1.0', b'version: link:../private'),
])
def test_pnpm_invalid_stale_or_unresolved_locks_are_incomplete(lock):
    scan = parse_stack({'web/package.json': b'{"dependencies":{"react":"^19"}}', 'pnpm-lock.yaml': lock}, 'web')
    assert not scan.complete
    assert 'private-marker' not in str(scan.issues)


def test_pnpm_root_peer_suffix_resolves_only_the_direct_package():
    lock = PNPM.replace(b'  web:', b'  .:').replace(b'version: 19.1.0}', b'version: 19.1.0(peer@1.0.0)}')
    lock = lock.replace(b'  react@19.1.0: {}', b'  react@19.1.0(peer@1.0.0): {dependencies: {scheduler: 1.0.0}}\n  scheduler@1.0.0: {}')
    lock = lock.replace(b'packages:\n', b'packages:\n  scheduler@1.0.0: {resolution: {integrity: sha512-test}}\n')
    scan = parse_stack({'package.json': b'{"dependencies":{"react":"^19"}}', 'pnpm-lock.yaml': lock})
    assert scan.complete, scan.issues
    assert {(d.name, d.resolved_version, d.direct) for d in scan.dependencies} == {('react', '19.1.0', True)}


def test_npm_ancestor_uses_nearest_node_modules_and_ignores_siblings():
    lock = {'lockfileVersion': 3, 'packages': {
        '': {}, 'web': {'dependencies': {'react': '^19'}},
        'node_modules/react': {'version': '18.3.1'},
        'web/node_modules/react': {'version': '19.1.0', 'dependencies': {'scheduler': '^1'}},
        'node_modules/scheduler': {'version': '1.0.0'},
        'sibling/node_modules/unrelated': {'version': '2.0.0'},
        'node_modules/web': {'link': True, 'resolved': 'web'},
    }}
    files = {'web/package.json': b'{"dependencies":{"react":"^19"}}', 'package-lock.json': json.dumps(lock).encode()}
    scan = parse_stack(files, 'web')
    assert scan.complete, scan.issues
    assert {(d.name, d.resolved_version, d.direct) for d in scan.dependencies} == {('react', '19.1.0', True)}
    lock['packages']['web']['dependencies']['react'] = '^18'
    files['package-lock.json'] = json.dumps(lock).encode()
    assert not parse_stack(files, 'web').complete


@pytest.mark.parametrize('version', [2, 3])
@pytest.mark.parametrize('root', ['', 'apps/web'])
def test_npm_local_lock_checks_importer_and_resolves_only_declarations(version, root):
    prefix = root + '/' if root else ''
    manifest = {'dependencies': {'react': '^19'}, 'optionalDependencies': {'optional': '^1'}}
    packages = {'': manifest,
        'node_modules/react': {'version': '19.1.0', 'dependencies': {'scheduler': '^1'}},
        'node_modules/scheduler': {'version': '1.0.0'},
        'node_modules/optional': {'version': '1.2.0', 'optional': True},
        'node_modules/unused': {'version': '2.0.0'}}
    files = {prefix + 'package.json': json.dumps(manifest).encode(),
        prefix + 'package-lock.json': json.dumps({'lockfileVersion': version, 'packages': packages}).encode()}
    scan = parse_stack(files, root)
    assert scan.complete, scan.issues
    assert {(d.name, d.resolved_version, d.role, d.direct) for d in scan.dependencies} == {
        ('react', '19.1.0', 'runtime', True),
        ('optional', '1.2.0', 'optional', True)}
    packages['']['dependencies'] = {'react': '^18'}
    files[prefix + 'package-lock.json'] = json.dumps({'lockfileVersion': version, 'packages': packages}).encode()
    assert not parse_stack(files, root).complete


@pytest.mark.parametrize('package', [
    {'version': '19.1.0', 'resolved': 'git+https://example.test/private#commit'},
    {'version': 'file:../private'},
    {'version': '19.1.0', 'link': True, 'resolved': '../private'},
])
def test_npm_local_lock_rejects_nonregistry_resolutions(package):
    files = {'package.json': b'{"dependencies":{"react":"^19"}}',
        'package-lock.json': json.dumps({'lockfileVersion': 3, 'packages': {
            '': {'dependencies': {'react': '^19'}}, 'node_modules/react': package}}).encode()}
    assert not parse_stack(files).complete


@pytest.mark.parametrize('duplicate_manifest', [True, False])
def test_duplicate_javascript_metadata_keys_cannot_claim_complete(duplicate_manifest):
    manifest = b'{"dependencies":{"react":"^19"}}'
    lock = b'{"lockfileVersion":3,"packages":{"":{"dependencies":{"react":"^19"}},"node_modules/react":{"version":"19.1.0"}}}'
    if duplicate_manifest:
        manifest = b'{"dependencies":{"react":"^18"},"dependencies":{"react":"^19"}}'
    else:
        lock = lock.replace(b'"version":"19.1.0"', b'"version":"18.3.1","version":"19.1.0"')
    scan = parse_stack({'package.json': manifest, 'package-lock.json': lock})
    assert not scan.complete


def test_conflicting_package_managers_and_deep_yaml_do_not_claim_complete():
    files = {'package.json': b'{}', 'package-lock.json': b'{"lockfileVersion":3,"packages":{"":{}}}',
        'pnpm-lock.yaml': b"lockfileVersion: '9.0'\nimporters: {'.': {}}\n"}
    assert not parse_stack(files).complete

    files.pop('package-lock.json')
    files['pnpm-lock.yaml'] = b'[' * 50 + b']' * 50
    assert not parse_stack(files).complete


def test_npm_ancestor_ignores_transitive_peer_dependencies():
    packages = {'web': {'dependencies': {'react-dom': '^19'}},
        'node_modules/react-dom': {'version': '19.1.0', 'peerDependencies': {'react': '^19', 'optional-peer': '*'},
            'peerDependenciesMeta': {'optional-peer': {'optional': True}}},
        'node_modules/react': {'version': '19.1.0'}}
    files = {'web/package.json': b'{"dependencies":{"react-dom":"^19"}}',
        'package-lock.json': json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()}
    scan = parse_stack(files, 'web')
    assert scan.complete, scan.issues
    assert {(d.name, d.resolved_version) for d in scan.dependencies} == {('react-dom', '19.1.0')}
    del packages['node_modules/react']
    files['package-lock.json'] = json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()
    assert parse_stack(files, 'web').complete


def test_npm_transitive_optional_and_required_branches_are_out_of_scope():
    manifest = {'dependencies': {'compiler': '^1'}}
    packages = {'': manifest,
        'node_modules/compiler': {'version': '1.0.0', 'optionalDependencies': {'wasi': '^1', 'missing-optional': '^2'}},
        'node_modules/wasi': {'version': '1.0.0', 'optional': True, 'dependencies': {'wasm-runtime': '^2'}}}
    files = {'package.json': json.dumps(manifest).encode(),
        'package-lock.json': json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()}
    scan = parse_stack(files)
    assert scan.complete, scan.issues
    assert {(dep.name, dep.resolved_version, dep.role) for dep in scan.dependencies} == {
        ('compiler', '1.0.0', 'runtime')}
    packages['node_modules/compiler']['dependencies'] = {'required-runtime': '^2'}
    files['package-lock.json'] = json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()
    assert parse_stack(files).complete


@pytest.mark.parametrize('optional', [False, True])
def test_npm_declared_root_peers_resolve_and_respect_optional_peers(optional):
    manifest = {'peerDependencies': {'react': '^19'}}
    if optional:
        manifest['peerDependenciesMeta'] = {'react': {'optional': True}}
    packages = {'': manifest, 'node_modules/react': {'version': '19.1.0', 'dependencies': {'scheduler': '^1'}},
                'node_modules/scheduler': {'version': '1.0.0'}}
    files = {'package.json': json.dumps(manifest).encode(),
        'package-lock.json': json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()}
    scan = parse_stack(files)
    assert scan.complete, scan.issues
    assert {(dep.name, dep.resolved_version, dep.role) for dep in scan.dependencies} == {
        ('react', '19.1.0', 'peer')}
    del packages['node_modules/react']
    files['package-lock.json'] = json.dumps({'lockfileVersion': 3, 'packages': packages}).encode()
    assert parse_stack(files).complete is optional


def test_pnpm_transitive_version_does_not_replace_direct_version():
    lock = PNPM.replace(b'  web:', b'  .:').replace(b'  react@19.1.0: {}', b'  react@19.1.0: {dependencies: {react: 18.3.1}}')
    scan = parse_stack({'package.json': b'{"dependencies":{"react":"^19"}}', 'pnpm-lock.yaml': lock})
    assert scan.complete, scan.issues
    assert {(dep.resolved_version, dep.direct) for dep in scan.dependencies} == {('19.1.0', True)}


def test_pnpm_patched_package_cannot_claim_ordinary_registry_coverage():
    lock = PNPM.replace(b'  web:', b'  .:').replace(b'version: 19.1.0}', b'version: 19.1.0(patch_hash=abc)}')
    lock = lock.replace(b'  react@19.1.0: {}', b'  react@19.1.0(patch_hash=abc): {}')
    lock += b'patchedDependencies: {react@19.1.0: {hash: abc, path: patches/react.patch}}\n'
    assert not parse_stack({'package.json': b'{"dependencies":{"react":"^19"}}', 'pnpm-lock.yaml': lock}).complete


def test_python_constraints_resolution_and_semantic_fingerprint():
    files = {
        'pyproject.toml': b'[project]\nname="demo"\ndependencies=["Fast_API>=1,<2"]\n',
        'uv.lock': b'version=1\n[[package]]\nname="fast-api"\nversion="1.2.3"\nsource={registry="https://pypi.org/simple"}\n',
    }
    scan = parse_stack(files)
    assert scan.complete
    dep = scan.dependencies[0]
    assert (dep.name, dep.declared_constraint, dep.resolved_version) == ('fast-api', '>=1,<2', '1.2.3')
    assert dep.documentation_target == '1.2.3'
    assert not dep.public_lookup_allowed
    files['pyproject.toml'] += b'\n[tool.random]\ncolor="red"\n'
    assert parse_stack(files).fingerprint == scan.fingerprint


def test_requirements_includes_are_bounded_and_cycles_incomplete():
    scan = parse_stack({'requirements.txt': b'-r extra.txt\n', 'extra.txt': b'-r requirements.txt\n'})
    assert not scan.complete
    assert any('cycle' in issue for issue in scan.issues)
    assert not parse_stack({'requirements.txt': b'-r ../outside.txt'}).complete


def test_application_scope_and_package_lock():
    scan = parse_stack({
        'package.json': b'{"dependencies":{"wrong":"1"}}',
        'web/package.json': b'{"dependencies":{"react":"^19"},"devDependencies":{"vite":"^7"}}',
        'web/package-lock.json': b'{"lockfileVersion":3,"packages":{"":{"dependencies":{"react":"^19"},"devDependencies":{"vite":"^7"}},"node_modules/react":{"version":"19.1.0"},"node_modules/vite":{"version":"7.0.0","dev":true}}}',
    }, 'web')
    assert scan.complete
    assert {dep.name for dep in scan.dependencies} == {'react', 'vite'}
    assert next(dep for dep in scan.dependencies if dep.name == 'react').resolved_version == '19.1.0'
    assert next(dep for dep in scan.dependencies if dep.name == 'vite').role == 'development'


def test_unsupported_and_ambiguous_inputs_do_not_claim_complete():
    assert not parse_stack({'pnpm-lock.yaml': b'lockfileVersion: 9'}).complete
    assert not parse_stack({'pyproject.toml': b'[project]\ndynamic=["dependencies"]'}).complete
    assert not parse_stack({'requirements.txt': b'private @ git+https://example.test/private'}).complete
    assert not parse_stack({'../package.json': b'{}'}).complete
    assert not parse_stack({'package.json': b'['}).complete
    assert not parse_stack({}).complete

def test_limits_private_names_and_ambiguous_versions():
    import docweave.integrations.stack as stack
    assert not parse_stack({'package.json': b' ' * (stack.MAX_FILE_BYTES + 1)}).complete
    assert not parse_stack({f'{n}.txt': b'' for n in range(stack.MAX_FILES + 1)}).complete
    scan = parse_stack({
        'package.json': b'{"dependencies":{"@company/internal":"^1"}}',
        'package-lock.json': b'{"lockfileVersion":3,"packages":{"node_modules/@company/internal":{"version":"1.0.0"},"node_modules/a/node_modules/@company/internal":{"version":"1.1.0"}}}',
    })
    assert not scan.complete
    assert not scan.dependencies[0].public_lookup_allowed
    assert scan.dependencies[0].documentation_target is None


def test_lock_order_does_not_change_fingerprint_and_missing_include_is_held():
    assert not parse_stack({'requirements.txt': b'-r missing.txt'}).complete
    first = parse_stack({'package.json': b'{"dependencies":{"b":"^2", "a":"1"}}'})
    second = parse_stack({'package.json': b'{ "name":"changed", "dependencies": { "a":"1", "b":"^2"} }'})
    assert first.fingerprint == second.fingerprint


def test_requirements_reject_options_and_preserve_extras_in_fingerprint():
    dangerous = parse_stack({'requirements.txt': b'fastapi>=1 --index-url https://private:secret123@private.test/simple'})
    assert not dangerous.complete
    assert 'secret123' not in repr(dangerous)
    plain = parse_stack({'requirements.txt': b'fastapi>=1'})
    extras = parse_stack({'requirements.txt': b'fastapi[standard]>=1'})
    assert plain.fingerprint != extras.fingerprint


@pytest.mark.parametrize('manager', ['npm', 'pnpm'])
def test_dependency_discovery_stops_at_direct_declarations(manager):
    manifest = b'{"dependencies":{"a":"^1"}}'
    if manager == 'npm':
        lock = json.dumps({'lockfileVersion':3,'packages':{'':{'dependencies':{'a':'^1'}},
            'node_modules/a':{'version':'1.0.0','dependencies':{'b':'^1'}},
            'node_modules/b':{'version':'1.0.0','dependencies':{'c':'^1'}},
            'node_modules/c':{'version':'1.0.0'}}}).encode()
        name='package-lock.json'
    else:
        lock=b"lockfileVersion: '9.0'\nimporters: {'.': {dependencies: {a: {specifier: ^1, version: 1.0.0}}}}\npackages: {a@1.0.0: {resolution: {integrity: sha512-a}}, b@1.0.0: {resolution: {integrity: sha512-b}}, c@1.0.0: {resolution: {integrity: sha512-c}}}\nsnapshots: {a@1.0.0: {dependencies: {b: 1.0.0}}, b@1.0.0: {dependencies: {c: 1.0.0}}, c@1.0.0: {}}\n"
        name='pnpm-lock.yaml'
    scan=parse_stack({'package.json':manifest,name:lock})
    assert scan.complete,scan.issues
    assert {(d.name,d.direct) for d in scan.dependencies}=={('a',True)}


def test_python_lock_stops_at_direct_declarations():
    raw=b'version=1\n[[package]]\nname="a"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\ndependencies=[{name="b"}]\n[[package]]\nname="b"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\ndependencies=[{name="c"}]\n[[package]]\nname="c"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\n'
    scan=parse_stack({'pyproject.toml':b'[project]\ndependencies=["a==1.0.0"]\n','uv.lock':raw})
    assert scan.complete,scan.issues
    assert {d.name for d in scan.dependencies}=={'a'}


def test_python_exact_root_ignores_transitive_other_version():
    raw=b'version=1\n[[package]]\nname="a"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\ndependencies=[{name="a",version="2.0.0"}]\n[[package]]\nname="a"\nversion="2.0.0"\nsource={registry="https://pypi.org/simple"}\n'
    scan=parse_stack({'pyproject.toml':b'[project]\ndependencies=["a==1.0.0"]\n','uv.lock':raw})
    assert scan.complete,scan.issues
    assert {(d.resolved_version,d.direct) for d in scan.dependencies}=={('1.0.0',True)}


def test_pnpm_direct_packages_are_stable_regardless_of_declaration_order():
    lock=b"lockfileVersion: '9.0'\nimporters: {'.': {dependencies: {a: {specifier: ^1, version: 1.0.0}, b: {specifier: ^1, version: 1.0.0}}}}\npackages: {a@1.0.0: {resolution: {integrity: sha512-a}}, b@1.0.0: {resolution: {integrity: sha512-b}}, c@1.0.0: {resolution: {integrity: sha512-c}}}\nsnapshots: {a@1.0.0: {dependencies: {c: 1.0.0}}, b@1.0.0: {dependencies: {a: 1.0.0}}, c@1.0.0: {}}\n"
    first=parse_stack({'package.json':b'{"dependencies":{"a":"^1","b":"^1"}}','pnpm-lock.yaml':lock})
    second=parse_stack({'package.json':b'{"dependencies":{"b":"^1","a":"^1"}}','pnpm-lock.yaml':lock})
    assert first.complete and second.complete
    assert {d.name for d in first.dependencies}=={'a','b'}
    assert first.fingerprint==second.fingerprint


@pytest.mark.parametrize('field', ['dependencies', 'optional-dependencies', 'dev-dependencies'])
def test_uv_virtual_root_keeps_explicit_reference_version(field):
    refs='[{name="a",version="1.0.0"}]'
    declaration=field+'='+refs if field=='dependencies' else field+'={test='+refs+'}'
    raw=('version=1\n[[package]]\nname="project"\nversion="1.0.0"\nsource={virtual="."}\n'+declaration+'\n[[package]]\nname="a"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\ndependencies=[{name="a",version="2.0.0"}]\n[[package]]\nname="a"\nversion="2.0.0"\nsource={registry="https://pypi.org/simple"}\n').encode()
    scan=parse_stack({'uv.lock':raw})
    assert scan.complete,scan.issues
    assert {(d.resolved_version,d.direct) for d in scan.dependencies}=={('1.0.0',True)}
