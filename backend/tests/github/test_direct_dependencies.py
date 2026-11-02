import json
import pytest
from docweave.integrations.stack import parse_stack

@pytest.mark.parametrize('role', ['dependencies','devDependencies','optionalDependencies','peerDependencies'])
def test_npm_keeps_only_declared_packages_and_resolves_versions(role):
    manifest={role:{'a':'^1'}}
    lock={'lockfileVersion':3,'packages':{'':manifest,'node_modules/a':{'version':'1.0.0','dependencies':{'missing-child':'^1'}}}}
    scan=parse_stack({'package.json':json.dumps(manifest).encode(),'package-lock.json':json.dumps(lock).encode()})
    assert scan.complete,scan.issues
    assert [(d.name,d.resolved_version,d.direct) for d in scan.dependencies]==[('a','1.0.0',True)]

def test_pnpm_does_not_expand_declared_packages():
    raw=b"lockfileVersion: '9.0'\nimporters: {'.': {dependencies: {a: {specifier: ^1, version: 1.0.0}}}}\npackages: {a@1.0.0: {resolution: {integrity: sha512-a}}}\nsnapshots: {a@1.0.0: {dependencies: {missing-child: 1.0.0}}}\n"
    scan=parse_stack({'package.json':b'{"dependencies":{"a":"^1"}}','pnpm-lock.yaml':raw})
    assert scan.complete,scan.issues
    assert [(d.name,d.resolved_version,d.direct) for d in scan.dependencies]==[('a','1.0.0',True)]

def test_uv_keeps_only_declared_package_versions():
    raw=b'version=1\n[[package]]\nname="a"\nversion="1.0.0"\nsource={registry="https://pypi.org/simple"}\ndependencies=[{name="b"}]\n[[package]]\nname="b"\nversion="2.0.0"\nsource={registry="https://pypi.org/simple"}\n'
    scan=parse_stack({'pyproject.toml':b'[project]\ndependencies=["a==1.0.0"]\n','uv.lock':raw})
    assert scan.complete,scan.issues
    assert [(d.name,d.resolved_version,d.direct) for d in scan.dependencies]==[('a','1.0.0',True)]

@pytest.mark.parametrize('version', ['123', '["1.0.0"]'])
def test_uv_rejects_non_string_direct_versions(version):
    raw=('version=1\n[[package]]\nname="a"\nversion='+version+'\nsource={registry="https://pypi.org/simple"}\n').encode()
    scan=parse_stack({'pyproject.toml':b'[project]\ndependencies=["a>=1"]\n','uv.lock':raw})
    assert not scan.complete

def test_pnpm_resolves_declared_peer_without_collecting_undeclared_children():
    raw=b"lockfileVersion: '9.0'\nimporters: {'.': {dependencies: {a: {specifier: ^1, version: 1.0.0(b@2.0.0)}}}}\npackages: {a@1.0.0: {resolution: {integrity: sha512-a}}, b@2.0.0: {resolution: {integrity: sha512-b}}}\nsnapshots: {a@1.0.0(b@2.0.0): {dependencies: {b: 2.0.0, undeclared: 3.0.0}}, b@2.0.0: {}}\n"
    scan=parse_stack({'package.json':b'{"dependencies":{"a":"^1"},"peerDependencies":{"b":"^2"}}','pnpm-lock.yaml':raw})
    assert scan.complete,scan.issues
    assert {(d.name,d.resolved_version,d.role,d.direct) for d in scan.dependencies}=={('a','1.0.0','runtime',True),('b','2.0.0','peer',True)}

def test_pnpm_declared_peer_prefers_its_direct_importer_version():
    raw=b"lockfileVersion: '9.0'\nimporters: {'.': {dependencies: {a: {specifier: ^1, version: 1.0.0}, b: {specifier: ^1, version: 1.0.0}}}}\npackages: {a@1.0.0: {resolution: {integrity: sha512-a}}, b@1.0.0: {resolution: {integrity: sha512-b}}, b@2.0.0: {resolution: {integrity: sha512-b2}}}\nsnapshots: {a@1.0.0: {dependencies: {b: 2.0.0}}, b@1.0.0: {}, b@2.0.0: {}}\n"
    scan=parse_stack({'package.json':b'{"dependencies":{"a":"^1","b":"^1"},"peerDependencies":{"b":"^1"}}','pnpm-lock.yaml':raw})
    assert scan.complete,scan.issues
    assert {(d.resolved_version,d.role) for d in scan.dependencies if d.name=='b'}=={('1.0.0','runtime'),('1.0.0','peer')}
