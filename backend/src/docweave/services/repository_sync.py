"""Commit-pinned static repository metadata scans. Call after the project lock."""
from dataclasses import replace
from pathlib import PurePosixPath

from docweave.core.errors import DomainError
from docweave.integrations.github import METADATA_NAMES, metadata_path, safe_path
from docweave.integrations.stack import parse_stack, SCAN_REVISION


async def scan_repository(client, token, repository_id, branch, application_path, previous_commit=None, previous_fingerprint=None):
    root = application_path
    if not isinstance(root, str) or (root and not safe_path(root)) or len(root.split("/")) > 8:
        raise DomainError("invalid_request")
    with client.request_budget(200):
        await client.repository(token, repository_id)
        commit = await client.head(token, repository_id, branch)
        if commit == previous_commit and isinstance(previous_fingerprint, str) and previous_fingerprint.startswith(SCAN_REVISION + ':'):
            await client.repository(token, repository_id)
            return {"commit_sha": commit, "scan": None, "unchanged": True}
        tree = await client.tree(token, repository_id, commit)
        issues = []
        entries = tree["tree"]
        if tree["truncated"]:
            issues.append("repository tree truncated")
        if len(entries) > 20_000:
            issues.append("repository tree entry limit exceeded")
        if any(not isinstance(row, dict) or not safe_path(row.get("path")) for row in entries[:20_001]):
            issues.append("invalid repository tree")
        elif len({row['path'] for row in entries[:20_001]}) != len(entries[:20_001]):
            issues.append('duplicate repository tree paths')
        if any(isinstance(row, dict) and metadata_path(row.get("path")) and len(row["path"].split("/")) > 8 for row in entries[:20_001]):
            issues.append("repository tree depth exceeded")
        files = {}
        if not issues:
            by_path = {row["path"]: row for row in entries}
            prefix = root + "/" if root else ""
            pending = sorted(path for path in by_path if path.startswith(prefix)
                and PurePosixPath(path).name in METADATA_NAMES and metadata_path(path))
            enclosing = set()
            manifests = [path for path in pending if PurePosixPath(path).name in ('package.json', 'pyproject.toml', 'requirements.txt', 'Pipfile')]
            for manifest in manifests:
                folder = PurePosixPath(manifest).parent
                for name in ('uv.lock', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'poetry.lock', 'Pipfile.lock'):
                    if name in ('package-lock.json', 'pnpm-lock.yaml', 'yarn.lock'):
                        if str(folder / 'package.json') not in by_path:
                            continue
                    elif not any(str(folder / candidate) in by_path for candidate in ('pyproject.toml', 'requirements.txt', 'Pipfile')):
                        continue
                    if str(folder / name) not in by_path:
                        path = next((str(parent / name) for parent in folder.parents
                            if str(parent / name) in by_path), None)
                        if path:
                            enclosing.add(path)
            pending.extend(sorted(enclosing))
            seen = set()
            total = 0
            while pending:
                path = pending.pop(0)
                if path in seen:
                    continue
                seen.add(path)
                if len(seen) > 100:
                    issues.append("metadata file count exceeded")
                    break
                row = by_path.get(path)
                if not row:
                    issues.append("missing requirements include")
                    continue
                if row.get("type") != "blob" or row.get("mode") not in ("100644", "100755"):
                    issues.append("symlink or submodule metadata skipped")
                    continue
                size = row.get("size")
                if type(size) is not int or size < 0 or size > 2 * 1024 * 1024:
                    issues.append("metadata file too large")
                    continue
                if total + size > 10 * 1024 * 1024:
                    issues.append("metadata total byte limit exceeded")
                    break
                data = (await client.files(token, repository_id, commit, [path]))[path]
                if len(data) != size:
                    issues.append("metadata size mismatch")
                    break
                total += len(data)
                if total > 10 * 1024 * 1024:
                    issues.append("metadata total byte limit exceeded")
                    break
                if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    issues.append("LFS metadata skipped")
                    continue
                files[path] = data
                if PurePosixPath(path).name in ("yarn.lock", "poetry.lock", "Pipfile", "Pipfile.lock"):
                    issues.append("unsupported dependency metadata")
                if path.endswith('pnpm-workspace.yaml') and str(PurePosixPath(path).parent / 'pnpm-lock.yaml') not in by_path:
                    issues.append('pnpm workspace requires a supported lock')
                if path in enclosing and PurePosixPath(path).name not in ('package-lock.json', 'pnpm-lock.yaml'):
                    issues.append("enclosing workspace lock requires scoped parsing")
                if path.endswith((".txt", ".in")):
                    try:
                        for line in data.decode("utf-8-sig").splitlines():
                            line = line.strip()
                            if line.startswith(("-r ", "--requirement ")):
                                relative = line.split(maxsplit=1)[1]
                                included = str(PurePosixPath(path).parent / relative)
                                if not safe_path(relative) or not metadata_path(included) or len(included.split("/")) > 8:
                                    issues.append("unsafe or unsupported requirements include")
                                else:
                                    pending.append(included)
                    except UnicodeError:
                        issues.append("invalid requirements encoding")
        scan = parse_stack(files, root)
        if issues:
            scan = replace(scan, complete=False, issues=tuple(sorted(set(scan.issues) | set(issues))))
        await client.repository(token, repository_id)
        return {"commit_sha": commit, "scan": scan, "unchanged": False}
