"""Bounded, offline dependency metadata extraction; never execute repository code."""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import PurePosixPath
import re
import tomllib
from docweave.integrations.javascript_locks import npm_dependencies, pnpm_dependencies
from docweave.integrations.github import metadata_path
from docweave.rag.contracts import unique_keys

MAX_FILES = 128
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
MAX_DEPENDENCIES = 10_000
SCAN_REVISION = 'repo-direct-v3'
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
    application_path: str = ''


@dataclass(frozen=True)
class StackScan:
    dependencies: tuple[Dependency, ...]
    complete: bool
    issues: tuple[str, ...]
    fingerprint: str


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith('/') and '\\' not in path and ':' not in path and all(part not in ('', '.', '..') for part in path.split('/'))


def _parse_application(files: dict[str, bytes], application_path: str = '') -> StackScan:
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
                packages = data.get('package', [])
                roots = [dep for dep in dependencies if dep.ecosystem == 'python' and dep.direct]
                if not roots:
                    for package in packages:
                        if not set(package.get('source', {})) & {'virtual', 'editable'}:
                            continue
                        for reference in package.get('dependencies', []):
                            requirement(reference['name'] + ('==' + reference['version'] if reference.get('version') else ''))
                        for field, role in (('optional-dependencies', 'optional'), ('dev-dependencies', 'development')):
                            for group in package.get(field, {}).values():
                                for reference in group:
                                    requirement(reference['name'] + ('==' + reference['version'] if reference.get('version') else ''), role)
                    roots = [dep for dep in dependencies if dep.ecosystem == 'python' and dep.direct]
                if not roots and packages:
                    raise ValueError('Python lock has no declared project roots')
                def locked_package(name, version=None):
                    matches = [package for package in packages
                        if re.sub(r'[-_.]+', '-', package['name']).lower() == name
                        and (version is None or package['version'] == version)]
                    if len(matches) != 1 or not isinstance(matches[0]['version'], str) or 'registry' not in matches[0].get('source', {}):
                        raise ValueError('unresolved Python lock dependency')
                    return matches[0]
                for dep in roots:
                    exact = dep.declared_constraint[2:] if dep.declared_constraint and re.fullmatch(r'==[^*,]+', dep.declared_constraint) else None
                    package = locked_package(dep.name, exact)
                    dependencies = [replace(item, resolved_version=package['version'], documentation_target=package['version'])
                        if item.direct and item.ecosystem == 'python' and item.name == dep.name and item.role == dep.role else item
                        for item in dependencies]
            elif filename == 'package.json':
                data = json.loads(raw, object_pairs_hook=unique_keys)
                for field, role in (('dependencies', 'runtime'), ('devDependencies', 'development'), ('optionalDependencies', 'optional'), ('peerDependencies', 'peer')):
                    for name, constraint in data.get(field, {}).items():
                        add(name, 'javascript', constraint, role)
                        if not re.fullmatch(r'[0-9v<>=~^*| .xX+-]+', constraint):
                            issues.append('nonregistry or unsupported JavaScript constraint')
            else:
                importer = str(PurePosixPath(root or '.').relative_to(PurePosixPath(path).parent))
                manifest = json.loads(usable[prefix + 'package.json'], object_pairs_hook=unique_keys)
                locked = (pnpm_dependencies if filename == 'pnpm-lock.yaml' else npm_dependencies)(raw, importer, manifest)
                direct_versions = {(name, role): version for name, version, role, direct in locked if direct}
                dependencies = [replace(dep, resolved_version=direct_versions[(dep.name, dep.role)],
                    documentation_target=direct_versions[(dep.name, dep.role)])
                    if dep.ecosystem == 'javascript' and (dep.name, dep.role) in direct_versions else dep for dep in dependencies]
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
    merged: list[Dependency] = []
    for dep in dependencies:
        versions = resolved.get((dep.ecosystem, dep.name), set())
        if dep.direct and dep.resolved_version:
            pass
        elif dep.direct and len(versions) == 1:
            version = next(iter(versions))
            dep = replace(dep, resolved_version=version, documentation_target=version)
        elif dep.direct and len(versions) > 1:
            issues.append('ambiguous resolved dependency versions')
        merged.append(dep)
    direct_versions = {(dep.ecosystem, dep.name, dep.role, dep.resolved_version) for dep in merged if dep.direct}
    merged = [dep for dep in merged if dep.direct or (dep.ecosystem, dep.name, dep.role, dep.resolved_version) not in direct_versions]
    unique = {json.dumps(asdict(dep), sort_keys=True): dep for dep in merged}
    ordered = tuple(unique[key] for key in sorted(unique))
    fingerprint = hashlib.sha256(json.dumps([asdict(dep) for dep in ordered], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return StackScan(ordered, not issues, tuple(sorted(set(issues))), fingerprint)


def parse_stack(files: dict[str, bytes], application_path: str = '') -> StackScan:
    """Discover metadata directories within scope, retaining each app's version identity."""
    root = application_path.rstrip('/')
    if (root and not _safe_path(root)) or any(not _safe_path(path) for path in files):
        return _parse_application(files, application_path)
    usable = {path: data for path, data in files.items() if metadata_path(path)}
    prefix = root + '/' if root else ''
    folders = sorted({'' if str(PurePosixPath(path).parent) == '.' else str(PurePosixPath(path).parent)
        for path in usable if path.startswith(prefix)
        and PurePosixPath(path).name in ('requirements.txt', 'pyproject.toml', 'uv.lock', 'package.json', 'Pipfile')})
    if not folders:
        return _parse_application(usable, root)
    dependencies, issues = [], set()
    for folder in folders:
        scan = _parse_application(usable, folder)
        issues.update(scan.issues)
        dependencies.extend(replace(dep, application_path=folder) for dep in scan.dependencies)
        if len(dependencies) > MAX_DEPENDENCIES:
            issues.add('dependency bounds exceeded')
            dependencies = dependencies[:MAX_DEPENDENCIES]
            break
    ordered = tuple(sorted(dependencies, key=lambda dep: json.dumps(asdict(dep), sort_keys=True)))
    fingerprint = SCAN_REVISION + ':' + hashlib.sha256(json.dumps([asdict(dep) for dep in ordered], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return StackScan(ordered, not issues, tuple(sorted(issues)), fingerprint)
