from docweave.integrations.stack import parse_stack


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
        'web/package-lock.json': b'{"lockfileVersion":3,"packages":{"":{},"node_modules/react":{"version":"19.1.0"},"node_modules/vite":{"version":"7.0.0","dev":true}}}',
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
