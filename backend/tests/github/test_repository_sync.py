"""Repository scans only read allowlisted metadata at the resolved commit."""
import base64
from urllib.parse import parse_qs

import httpx2
import pytest

from tests.github.test_github import configuration

pytestmark = pytest.mark.anyio
SHA = "a" * 40


def fixture_client(files=None, *, truncated=False, revoked=False, entries=None):
    from docweave.core.github_settings import GitHubSettings
    from docweave.integrations.github import GitHubClient
    requests = []
    files = files if files is not None else {"web/package.json": b'{"dependencies":{"react":"^19"}}'}
    tree = entries if entries is not None else [{"path": path, "type": "blob", "mode": "100644", "size": len(data), "sha": "b" * 40} for path, data in files.items()]
    checks = 0
    async def provider(request):
        nonlocal checks
        requests.append(request)
        path = request.url.path
        if path == "/user/installations":
            checks += 1
            return httpx2.Response(200, json={"installations": [] if revoked and checks >= 3 else [{"id": 7}]})
        if path == "/user/installations/7/repositories":
            return httpx2.Response(200, json={"repositories": [{"id": 42, "name": "repo", "default_branch": "main"}]})
        if path == "/repositories/42/commits/main":
            return httpx2.Response(200, json={"sha": SHA})
        if path == f"/repositories/42/git/trees/{SHA}":
            return httpx2.Response(200, json={"tree": tree, "truncated": truncated})
        if path.startswith("/repositories/42/contents/"):
            name = path.removeprefix("/repositories/42/contents/")
            assert parse_qs(request.url.query.decode())["ref"] == [SHA]
            data = files[name]
            return httpx2.Response(200, json={"type": "file", "encoding": "base64", "size": len(data),
                "content": base64.b64encode(data).decode()})
        raise AssertionError(path)
    return GitHubClient(GitHubSettings.load(configuration()), transport=httpx2.MockTransport(provider)), requests


async def test_scan_pins_reads_to_one_commit_and_skips_source_files():
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client({"web/package.json": b'{"dependencies":{"react":"^19"}}', "web/source.ts": b"secret source"})
    result = await scan_repository(client, "token", 42, "main", "web")
    assert result["commit_sha"] == SHA and not result["unchanged"]
    assert result["scan"].complete
    assert [dep.name for dep in result["scan"].dependencies] == ["react"]
    assert len([request for request in requests if "/contents/" in request.url.path]) == 1


async def test_same_commit_checks_access_without_tree_or_download():
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client()
    result = await scan_repository(client, "token", 42, "main", "web", previous_commit=SHA)
    assert result == {"commit_sha": SHA, "scan": None, "unchanged": True}
    assert not any("/contents/" in request.url.path or "/trees/" in request.url.path for request in requests)


async def test_truncated_tree_returns_explicit_incomplete_without_downloads():
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client(truncated=True)
    result = await scan_repository(client, "token", 42, "main", "web")
    assert not result["scan"].complete and "repository tree truncated" in result["scan"].issues
    assert not any("/contents/" in request.url.path for request in requests)


async def test_revoked_app_access_prevents_scan_publication():
    from docweave.services.repository_sync import scan_repository
    from docweave.core.errors import DomainError
    client, _ = fixture_client(revoked=True)
    with pytest.raises(DomainError, match="not_found"):
        await scan_repository(client, "token", 42, "main", "web")


@pytest.mark.parametrize("entry,reason", [
    ({"path": "web/package.json", "mode": "120000", "type": "blob", "size": 4}, "symlink or submodule metadata skipped"),
    ({"path": "web/package.json", "mode": "100644", "type": "blob", "size": 2 * 1024 * 1024 + 1}, "metadata file too large"),
    ({"path": "web/package.json", "mode": "160000", "type": "commit", "size": 4}, "symlink or submodule metadata skipped"),
])
async def test_metadata_bounds_and_indirections_are_incomplete(entry, reason):
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client(entries=[entry])
    result = await scan_repository(client, "token", 42, "main", "web")
    assert not result["scan"].complete and reason in result["scan"].issues
    assert not any("/contents/" in request.url.path for request in requests)


async def test_requirements_include_static_text_only_and_missing_is_incomplete():
    from docweave.services.repository_sync import scan_repository
    client, requests = fixture_client({"requirements.txt": b"-r requirements/base.txt\n", "requirements/base.txt": b"fastapi==1.2.3\n", "danger.py": b"do not read"})
    result = await scan_repository(client, "token", 42, "main", "")
    assert result["scan"].complete
    assert result["scan"].dependencies[0].name == "fastapi"
    assert not any("danger.py" in request.url.path for request in requests)


async def test_lfs_pointer_and_ancestor_locks_cannot_claim_complete():
    from docweave.services.repository_sync import scan_repository
    client, _ = fixture_client({"web/package.json": b"version https://git-lfs.github.com/spec/v1\noid sha256:private\n", "package-lock.json": b"{}"})
    result = await scan_repository(client, "token", 42, "main", "web")
    assert not result["scan"].complete
    assert "LFS metadata skipped" in result["scan"].issues
    assert any('package-lock.json' in issue for issue in result['scan'].issues)


async def test_pnpm_ancestor_is_fetched_at_pinned_sha_and_scoped():
    from docweave.services.repository_sync import scan_repository
    from tests.github.test_stack import PNPM
    client, requests = fixture_client({'web/package.json': b'{"dependencies":{"react":"^19"}}',
        'pnpm-lock.yaml': PNPM, 'pnpm-workspace.yaml': b'packages: [web, sibling]',
        'sibling/package.json': b'{"dependencies":{"wrong":"1"}}'})
    result = await scan_repository(client, 'token', 42, 'main', 'web')
    assert result['scan'].complete, result['scan'].issues
    assert [(dep.name, dep.resolved_version) for dep in result['scan'].dependencies] == [('react', '19.1.0')]
    assert not any('sibling/package.json' in request.url.path for request in requests)


async def test_duplicate_tree_paths_cannot_silently_select_metadata():
    from docweave.services.repository_sync import scan_repository
    row = {'path': 'web/package.json', 'mode': '100644', 'type': 'blob', 'size': 2}
    client, requests = fixture_client({'web/package.json': b'{}'}, entries=[row, row])
    result = await scan_repository(client, 'token', 42, 'main', 'web')
    assert not result['scan'].complete
    assert not any('/contents/' in request.url.path for request in requests)


@pytest.mark.parametrize("application_path", ["../web", "web/../app", "/web", "web\\app", "web//app"])
async def test_invalid_application_paths_are_rejected_before_github(application_path):
    from docweave.services.repository_sync import scan_repository
    from docweave.core.errors import DomainError
    client, requests = fixture_client()
    with pytest.raises(DomainError, match="invalid_request"):
        await scan_repository(client, "token", 42, "main", application_path)
    assert not requests


async def test_tree_entry_and_depth_limits_do_not_download():
    from docweave.services.repository_sync import scan_repository
    for entries, reason in (([{"path": f"file{index}", "type": "blob"} for index in range(20_001)], "repository tree entry limit exceeded"),
                            ([{"path": "a/b/c/d/e/f/g/h/package.json", "type": "blob"}], "repository tree depth exceeded")):
        client, requests = fixture_client(entries=entries)
        result = await scan_repository(client, "token", 42, "main", "")
        assert not result["scan"].complete and reason in result["scan"].issues
        assert not any("/contents/" in request.url.path for request in requests)


async def test_request_budget_fails_before_extra_request_and_is_task_local():
    from docweave.core.errors import DomainError
    client, requests = fixture_client()
    with client.request_budget(1):
        await client.installations("token")
        with pytest.raises(DomainError, match="not_ready"):
            await client.installations("token")
    assert len(requests) == 1
    await client.installations("token")
    assert len(requests) == 2


async def test_file_count_bounds_and_unsupported_locks_are_explicit():
    from docweave.services.repository_sync import scan_repository
    files = {"requirements.txt": b"-r file0.txt\n", **{f"file{index}.txt": f"-r file{index + 1}.txt\n".encode() for index in range(101)}}
    client, requests = fixture_client(files)
    result = await scan_repository(client, "token", 42, "main", "")
    assert not result["scan"].complete and "metadata file count exceeded" in result["scan"].issues
    assert len([request for request in requests if "/contents/" in request.url.path]) == 100
    client, _ = fixture_client({"package.json": b"{}", "yarn.lock": b"# yarn"})
    result = await scan_repository(client, "token", 42, "main", "")
    assert not result["scan"].complete and "unsupported dependency metadata" in result["scan"].issues


async def test_total_byte_limit_prevents_excess_metadata_downloads():
    from docweave.services.repository_sync import scan_repository
    files = {name: b" " * (1900 * 1024) for name in ("requirements.txt", "package.json", "pyproject.toml", "uv.lock", "package-lock.json", "pnpm-lock.yaml")}
    client, requests = fixture_client(files)
    result = await scan_repository(client, "token", 42, "main", "")
    assert not result["scan"].complete and "metadata total byte limit exceeded" in result["scan"].issues
    assert len([request for request in requests if "/contents/" in request.url.path]) == 5
