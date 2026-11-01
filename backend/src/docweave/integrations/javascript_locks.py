"""Static, importer-scoped registry lock resolution; never run a package manager."""
import json
from pathlib import PurePosixPath
import re

import yaml

FIELDS = (('dependencies', 'runtime'), ('devDependencies', 'development'), ('optionalDependencies', 'optional'))
VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?')
NAME = re.compile(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+')


class MetadataLoader(yaml.SafeLoader):
    """Reject aliases, duplicate keys and excessive composition before construction."""
    depth = 0
    nodes = 0

    def compose_node(self, parent, index):
        self.depth += 1
        self.nodes += 1
        try:
            if self.check_event(yaml.AliasEvent) or self.depth > 40 or self.nodes > 100_000:
                raise ValueError('unsupported YAML structure')
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError('duplicate YAML key')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def pnpm_dependencies(raw, importer, manifest):
    try:
        data = yaml.load(raw, Loader=MetadataLoader)
    except yaml.YAMLError:
        raise ValueError('invalid pnpm metadata') from None
    if str(data['lockfileVersion']) != '9.0':
        raise ValueError('unsupported pnpm version')
    selected = data['importers'][importer or '.']
    packages, snapshots = data.get('packages', {}), data.get('snapshots', {})
    result, pending, seen = [], [], set()
    for field, role in FIELDS:
        declared, locked = manifest.get(field, {}), selected.get(field, {})
        if declared.keys() != locked.keys():
            raise ValueError('stale pnpm importer')
        for name, constraint in declared.items():
            entry = locked[name]
            if entry['specifier'] != constraint:
                raise ValueError('stale pnpm specifier')
            pending.append((name, entry['version'], role, True))
    while pending:
        name, reference, role, direct = pending.pop()
        if not NAME.fullmatch(name) or not isinstance(reference, str):
            raise ValueError('unsupported pnpm reference')
        version = reference.split('(', 1)[0]
        if not VERSION.fullmatch(version) or 'patch_hash=' in reference:
            raise ValueError('nonregistry pnpm reference')
        key = name + '@' + reference
        result.append((name, version, role, direct))
        if len(result) > 10_000:
            raise ValueError('dependency bounds exceeded')
        if (key, role) in seen:
            continue
        seen.add((key, role))
        package = packages[name + '@' + version]
        if package.get('patched') or name + '@' + version in data.get('patchedDependencies', {}):
            raise ValueError('patched pnpm package unsupported')
        resolution = package['resolution']
        if not resolution.get('integrity') or set(resolution) - {'integrity'}:
            raise ValueError('nonregistry pnpm resolution')
        snapshot = snapshots[key]
        for field in ('dependencies', 'optionalDependencies'):
            for child, value in snapshot.get(field, {}).items():
                pending.append((child, value, 'optional' if field == 'optionalDependencies' else role, False))
    return result


def npm_dependencies(raw, importer, manifest):
    data = json.loads(raw)
    if data.get('lockfileVersion') not in (2, 3):
        raise ValueError('unsupported npm version')
    packages = data['packages']
    selected = packages[importer]
    pending, seen, result = [], set(), []
    for field, role in FIELDS:
        if manifest.get(field, {}) != selected.get(field, {}):
            raise ValueError('stale npm importer')
        pending.extend((importer, name, role, True, False) for name in manifest.get(field, {}))
    while pending:
        location, name, role, direct, optional_peer = pending.pop()
        if not NAME.fullmatch(name):
            raise ValueError('invalid npm name')
        parents = (PurePosixPath(location), *PurePosixPath(location).parents)
        found = next((str(parent / 'node_modules' / name) for parent in parents
            if parent.name != 'node_modules' and str(parent / 'node_modules' / name) in packages), None)
        if found is None:
            if optional_peer:
                continue
            raise ValueError('missing npm resolution')
        package = packages[found]
        version = package['version']
        if package.get('link') or not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError('unsupported npm resolution')
        resolved = package.get('resolved', '')
        if resolved and not resolved.startswith('https://registry.npmjs.org/'):
            raise ValueError('nonregistry npm resolution')
        result.append((name, version, role, direct))
        if len(result) > 10_000:
            raise ValueError('dependency bounds exceeded')
        if (found, role) in seen:
            continue
        seen.add((found, role))
        for field in ('dependencies', 'optionalDependencies'):
            pending.extend((found, child, 'optional' if field == 'optionalDependencies' else role, False, False)
                for child in package.get(field, {}))
        for child in package.get('peerDependencies', {}):
            optional_peer = package.get('peerDependenciesMeta', {}).get(child, {}).get('optional') is True
            pending.append((found, child, 'optional' if optional_peer else role, False, optional_peer))
    return result
