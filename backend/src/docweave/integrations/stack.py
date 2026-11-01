"""Bounded, offline dependency metadata extraction; never execute repository code."""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import PurePosixPath
import re
import tomllib
from docweave.integrations.javascript_locks import npm_dependencies, pnpm_dependencies

MAX_FILES = 128
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
MAX_DEPENDENCIES = 10_000
_NAME = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[A-Za-z0-9,._-]+\])?\s*([<>=!~].*)?$')


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    name: str
    declared_constraint: str | None = None
    resolved_version: str | None = None
    role: str = 'runtime'
    direct: bool = True
    documentation_target: str | None = None
    # Names alone do not establish public provenance; catalog policy must approve lookup.
    public_lookup_allowed: bool = False
    extras: tuple[str, ...] = ()


@dataclass(frozen=True)
class StackScan:
    dependencies: tuple[Dependency, ...]
    complete: bool
    issues: tuple[str, ...]
    fingerprint: str


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith('/') and '\\' not in path and ':' not in path and all(part not in ('', '.', '..') for part in path.split('/'))


def parse_stack(files: dict[str, bytes], application_path: str = '') -> StackScan:
    """Parse supplied SHA-pinned files. Missing includes/unsupported formats fail closed.

    A fingerprint describes dependency facts only, and must only replace memory
    when complete is true. No registry lookup or documentation version guessing.
    """
    issues: list[str] = []
    dependencies: list[Dependency] = []
    root = application_path.rstrip('/')
    if root and not _safe_path(root):
        issues.append('invalid application path')
    if len(files) > MAX_FILES or sum(len(value) for value in files.values()) > MAX_TOTAL_BYTES:
        issues.append('metadata bounds exceeded')
    usable: dict[str, bytes] = {}
    if not issues:
        for path, data in files.items():
            if not _safe_path(path) or len(data) > MAX_FILE_BYTES:
                issues.append('invalid path or oversized metadata')
            else:
                usable[path] = data
    prefix = root + '/' if root else ''

    def add(name, ecosystem, constraint=None, role='runtime', version=None, direct=True):
        if not isinstance(name, str) or not name or not all(isinstance(value, str) for value in (constraint, version) if value is not None):
            raise ValueError('invalid dependency')
        name = re.sub(r'[-_.]+', '-', name).lower() if ecosystem == 'python' else name.lower()
        dependencies.append(Dependency(ecosystem, name, constraint, version, role, direct, version))
        if len(dependencies) > MAX_DEPENDENCIES:
            raise ValueError('dependency bounds exceeded')

    def requirement(value, role='runtime'):
        if not isinstance(value, str):
            raise ValueError('invalid requirement')
        value = value.split(' #', 1)[0].strip()
        if not value or value.startswith('#'):
            return
        match = _NAME.fullmatch(value)
        if not match or ';' in value or (match[3] and not re.fullmatch(r'(?:===|==|!=|~=|<=|>=|<|>)[A-Za-z0-9.*+!_-]+(?:\s*,\s*(?:===|==|!=|~=|<=|>=|<|>)[A-Za-z0-9.*+!_-]+)*', match[3].strip())):
            raise ValueError('unsupported requirement syntax')
        add(match[1], 'python', (match[3] or '').replace(' ', '') or None, role)
        if match[2]:
            dependencies[-1] = replace(dependencies[-1], extras=tuple(sorted(part.lower() for part in match[2][1:-1].split(','))))

    def requirements(path, active=()):
        if path in active:
            raise ValueError('requirements include cycle')
        if len(active) >= 16 or path not in usable:
            raise ValueError('missing or excessive requirements includes')
        for line in usable[path].decode('utf-8-sig').splitlines():
            line = line.strip()
            if line.startswith(('-r ', '--requirement ')):
                relative = line.split(maxsplit=1)[1]
                if not _safe_path(relative):
                    raise ValueError('unsafe requirements include')
                requirements(str(PurePosixPath(path).parent / relative), (*active, path))
            else:
                requirement(line)

    locks = {}
    parents = (PurePosixPath(root or '.'),)
    if prefix + 'package.json' in usable:
        parents += tuple(PurePosixPath(root or '.').parents)
    for name in ('package-lock.json', 'pnpm-lock.yaml'):
        for parent in parents:
            if str(parent / name) in usable:
                locks[name] = str(parent / name)
                break
    if len(locks) > 1:
        issues.append('multiple JavaScript lockfiles require review')
    recognized = False
    for filename in ('requirements.txt', 'pyproject.toml', 'uv.lock', 'package.json', 'package-lock.json', 'pnpm-lock.yaml'):
        path = locks.get(filename, prefix + filename)
        if path not in usable:
            continue
        recognized = True
        try:
            raw = usable[path].decode('utf-8-sig')
            if filename == 'requirements.txt':
                requirements(path)
            elif filename == 'pyproject.toml':
                data = tomllib.loads(raw)
                project = data.get('project', {})
                if 'dependencies' in project.get('dynamic', []):
                    raise ValueError('dynamic Python dependencies unsupported')
                if not project and data.get('tool', {}).get('poetry'):
                    raise ValueError('Poetry metadata unsupported')
                for value in project.get('dependencies', []):
                    requirement(value)
                for group in project.get('optional-dependencies', {}).values():
                    for value in group:
                        requirement(value, 'optional')
                for group in data.get('dependency-groups', {}).values():
                    for value in group:
                        requirement(value, 'development')
                if data.get('tool', {}).get('uv', {}).get('sources'):
                    raise ValueError('custom uv sources require review')
            elif filename == 'uv.lock':
                data = tomllib.loads(raw)
                for package in data.get('package', []):
                    source = package.get('source', {})
                    if 'registry' not in source:
                        if 'virtual' in source or 'editable' in source:
                            continue
                        raise ValueError('nonregistry uv source unsupported')
                    add(package['name'], 'python', version=package['version'], direct=False)
            elif filename == 'package.json':
                data = json.loads(raw)
                if data.get('workspaces'):
                    raise ValueError('workspace dependency expansion unsupported')
                for field, role in (('dependencies', 'runtime'), ('devDependencies', 'development'), ('optionalDependencies', 'optional'), ('peerDependencies', 'peer')):
                    for name, constraint in data.get(field, {}).items():
                        add(name, 'javascript', constraint, role)
                        if not re.fullmatch(r'[0-9v<>=~^*| .xX+-]+', constraint):
                            issues.append('nonregistry or unsupported JavaScript constraint')
            elif filename == 'package-lock.json' and path == prefix + filename:
                data = json.loads(raw)
                if data.get('lockfileVersion') not in (2, 3) or not isinstance(data.get('packages'), dict):
                    raise ValueError('unsupported npm lock format')
                for location, package in data['packages'].items():
                    if not location:
                        continue
                    if package.get('link') or 'node_modules/' not in location:
                        raise ValueError('npm linked package unsupported')
                    name = location.rsplit('node_modules/', 1)[1]
                    add(name, 'javascript', version=package['version'], role='development' if package.get('dev') else 'runtime', direct=False)
            else:
                importer = str(PurePosixPath(root or '.').relative_to(PurePosixPath(path).parent))
                manifest = json.loads(usable[prefix + 'package.json'])
                locked = (pnpm_dependencies if filename == 'pnpm-lock.yaml' else npm_dependencies)(raw, importer, manifest)
                direct_versions = {(name, role): version for name, version, role, direct in locked if direct}
                dependencies = [replace(dep, resolved_version=direct_versions[(dep.name, dep.role)],
                    documentation_target=direct_versions[(dep.name, dep.role)])
                    if dep.ecosystem == 'javascript' and (dep.name, dep.role) in direct_versions else dep for dep in dependencies]
                for name, version, role, direct in locked:
                    if not direct:
                        add(name, 'javascript', version=version, role=role, direct=False)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            # Never include parser exception text: repository input can contain credentials.
            reason = str(error) if type(error) is ValueError and str(error) in {
                'requirements include cycle', 'unsafe requirements include', 'missing or excessive requirements includes',
            } else 'unsupported or malformed metadata'
            issues.append(f'{filename}: {reason}')
    if not recognized:
        issues.append('no supported dependency metadata')

    resolved: dict[tuple[str, str], set[str]] = {}
    for dep in dependencies:
        if dep.resolved_version:
            resolved.setdefault((dep.ecosystem, dep.name), set()).add(dep.resolved_version)
    if any(len(versions) > 1 for versions in resolved.values()):
        issues.append('ambiguous resolved dependency versions')
    merged: list[Dependency] = []
    direct_names = {(dep.ecosystem, dep.name) for dep in dependencies if dep.direct}
    for dep in dependencies:
        versions = resolved.get((dep.ecosystem, dep.name), set())
        if dep.direct and dep.resolved_version:
            pass
        elif dep.direct and len(versions) == 1:
            version = next(iter(versions))
            dep = replace(dep, resolved_version=version, documentation_target=version)
        elif dep.direct and len(versions) > 1:
            issues.append('ambiguous resolved dependency versions')
        if dep.direct or (dep.ecosystem, dep.name) not in direct_names:
            merged.append(dep)
    unique = {json.dumps(asdict(dep), sort_keys=True): dep for dep in merged}
    ordered = tuple(unique[key] for key in sorted(unique))
    fingerprint = hashlib.sha256(json.dumps([asdict(dep) for dep in ordered], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return StackScan(ordered, not issues, tuple(sorted(set(issues))), fingerprint)
