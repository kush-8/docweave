"""Construct structured stack memory; callers serialize publication per project."""
from dataclasses import asdict
import re
from uuid import UUID, uuid5


def update_memory(project_id, existing_stack, fingerprint, revision, scan, commit_sha, *, application_path=''):
    if not scan.complete:
        raise ValueError("An incomplete scan cannot replace project memory")
    if not isinstance(project_id, UUID) or not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_sha):
        raise ValueError("Invalid project or commit identity")
    if type(revision) is not int or not 1 <= revision < 2147483647:
        raise ValueError("Invalid context revision")
    changed = scan.fingerprint != fingerprint
    stack = existing_stack
    if changed:
        previous = {(entry.get("ecosystem"), entry.get("technology"), entry.get("role", "runtime"), entry.get('application_path', application_path),
            None if entry.get('direct', True) else entry.get('resolved_version')): entry.get("id") for entry in existing_stack}
        stack = []
        for dependency in scan.dependencies:
            key = dependency.ecosystem + ":" + dependency.name + ":" + dependency.role
            if dependency.application_path:
                key = dependency.application_path + ':' + key
            if not dependency.direct:
                key += ':resolved:' + (dependency.resolved_version or '')
            identity = previous.get((dependency.ecosystem, dependency.name, dependency.role, dependency.application_path,
                None if dependency.direct else dependency.resolved_version)) or str(uuid5(project_id, key))
            stack.append({**asdict(dependency), "id": identity, "technology": dependency.name,
                "declared_version": dependency.declared_constraint, "docs_target": dependency.documentation_target})
    return {"stack": stack, "stack_fingerprint": scan.fingerprint,
        "last_commit_sha": commit_sha, "context_revision": revision + int(changed)}
