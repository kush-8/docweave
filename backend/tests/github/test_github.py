"""GitHub transport and identity checks use no network or development database."""
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from cryptography.fernet import Fernet
from tests.database.test_database import databases, test_urls  # noqa: F401 -- guarded disposable database

pytestmark = pytest.mark.anyio


def configuration(**overrides):
    return {"APP_ORIGIN": "https://app.example.test", "GITHUB_CLIENT_ID": "client",
            "GITHUB_CLIENT_SECRET": "secret", "AUTH_ENCRYPTION_KEY": Fernet.generate_key().decode(), **overrides}


async def test_settings_normalize_origin_and_hide_secrets():
    from docweave.core.github_settings import GitHubSettings
    settings = GitHubSettings.load(configuration(APP_ORIGIN="https://APP.EXAMPLE.TEST:443/"))
    assert settings.origin == "https://app.example.test"
    assert settings.callback == settings.origin + "/api/v1/auth/callback"
    assert "secret" not in repr(settings) and settings.encryption_key not in repr(settings)
    assert GitHubSettings.load({}) is None


async def test_optional_app_slug_provides_only_fixed_github_installation_url():
    from docweave.core.github_settings import GitHubSettings
    assert GitHubSettings.load(configuration()).installation_url is None
    assert GitHubSettings.load(configuration(GITHUB_APP_SLUG="docweave-app")).installation_url == "https://github.com/apps/docweave-app/installations/new"
    for slug in ("../evil", "https://evil.test", "x?state=secret", "app/evil", "-app", "UPPER"):
        with pytest.raises(ValueError):
            GitHubSettings.load(configuration(GITHUB_APP_SLUG=slug))


@pytest.mark.parametrize("overrides", [{"APP_ORIGIN": "http://example.test"},
    {"APP_ORIGIN": "https://user:pass@example.test"}, {"APP_ORIGIN": "https://example.test/path"},
    {"GITHUB_CLIENT_SECRET": ""}, {"AUTH_ENCRYPTION_KEY": "bad"}, {"AUTH_LOCALHOST_HTTP": "yes"},
    {"AUTH_LOCALHOST_HTTP": "true"}])
async def test_settings_fail_closed(overrides):
    from docweave.core.github_settings import GitHubSettings
    with pytest.raises(ValueError):
        GitHubSettings.load(configuration(**overrides))


async def test_pkce_and_token_exchange_are_bound_without_query_secrets():
    from docweave.core.github_settings import GitHubSettings
    from docweave.integrations.github import GitHubClient
    requests = []
    async def provider(request):
        requests.append(request)
        return httpx2.Response(200, json={"access_token": "private", "expires_in": 28800,
            "refresh_token": "refresh", "refresh_token_expires_in": 100000})
    client = GitHubClient(GitHubSettings.load(configuration()), transport=httpx2.MockTransport(provider))
    query = parse_qs(urlsplit(client.authorize_url("state", "verifier")).query)
    assert query["state"] == ["state"] and query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in query and "secret" not in query
    token = await client.exchange_code("code", "verifier")
    assert token["access_token"] == "private" and token["expires_at"] > 0
    form = parse_qs(requests[0].content.decode())
    assert form["code_verifier"] == ["verifier"] and form["client_secret"] == ["secret"]
    assert "secret" not in str(requests[0].url)


async def test_repositories_are_user_app_intersection_and_branches_recheck_access():
    from docweave.core.github_settings import GitHubSettings
    from docweave.integrations.github import GitHubClient
    requests = []
    async def provider(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer user-token"
        data = {
            "/user/installations": {"installations": [{"id": 7}]},
            "/user/installations/7/repositories": {"repositories": [{"id": 42, "full_name": "owner/repo",
                "name": "repo", "private": True, "default_branch": "main", "description": "safe"}]},
            "/repositories/42/branches": [{"name": "main", "commit": {"sha": "a" * 40}}],
            "/repositories/42/commits/feature%2Fbranch": {"sha": "b" * 40},
        }
        return httpx2.Response(200, json=data.get(request.url.raw_path.decode().split("?")[0], {}))
    client = GitHubClient(GitHubSettings.load(configuration()), transport=httpx2.MockTransport(provider))
    repos = await client.repositories("user-token")
    assert repos[0]["id"] == 42 and repos[0]["installation_id"] == 7
    assert (await client.branches("user-token", 42))[0]["name"] == "main"
    assert await client.head("user-token", 42, "feature/branch") == "b" * 40
    from docweave.core.errors import DomainError
    with pytest.raises(DomainError, match="not_found"):
        await client.branches("user-token", 99)
    assert not any("/repositories/99/" in str(request.url) for request in requests)


async def test_upstream_errors_do_not_disclose_secrets_or_retry():
    from docweave.core.github_settings import GitHubSettings
    from docweave.integrations.github import GitHubClient
    from docweave.core.errors import DomainError
    calls = []
    async def provider(request):
        calls.append(request)
        return httpx2.Response(401, json={"error": "private-marker"})
    client = GitHubClient(GitHubSettings.load(configuration()), transport=httpx2.MockTransport(provider))
    with pytest.raises(DomainError) as exc:
        await client.user("private-access-token")
    assert "private" not in str(exc.value) and len(calls) == 1


@pytest.mark.parametrize("payload", [{"id": True, "login": "person"}, {"id": "12", "login": "person"},
    {"id": 12, "login": ""}, {"id": 0, "login": "person"}])
async def test_identity_requires_stable_numeric_id(payload):
    from docweave.integrations.github import validate_user
    from docweave.core.errors import DomainError
    with pytest.raises(DomainError):
        validate_user(payload)


async def test_identity_does_not_require_or_claim_verified_email():
    from docweave.integrations.github import validate_user
    assert validate_user({"id": 12, "login": "person", "email": None}) == {"id": 12, "login": "person", "name": "person"}


@pytest.fixture
async def github_login(databases):
    import time
    from docweave.core.github_settings import GitHubSettings
    from docweave.integrations.github import GitHubClient
    from docweave.services.github_auth import begin_login, complete_login
    owner, runtime = databases
    settings = GitHubSettings.load(configuration())
    state = {"identity": 12, "refreshes": 0, "unavailable": False}
    async def provider(request):
        if request.url.path == "/login/oauth/access_token":
            if b"refresh_token" in request.content:
                state["refreshes"] += 1
            return httpx2.Response(200, json={"access_token": "private-token", "expires_in": 28800,
                "refresh_token": "private-refresh", "refresh_token_expires_in": 100000})
        if state["unavailable"]:
            return httpx2.Response(503, json={})
        return httpx2.Response(200, json={"id": state["identity"], "login": "person", "email": None})
    client = GitHubClient(settings, transport=httpx2.MockTransport(provider))
    url, browser = await begin_login(settings, runtime, client, "127.0.0.1", "")
    params = {"state": parse_qs(urlsplit(url).query)["state"][0], "code": "code"}
    cookie, _ = await complete_login(settings, runtime, client, params, browser, "")
    return settings, runtime, owner, client, state, cookie, params, browser


async def test_github_callback_is_single_use_email_optional_and_tokens_encrypted(github_login):
    from sqlalchemy import text
    from docweave.core.errors import DomainError
    from docweave.services.github_auth import complete_login, session_context
    settings, runtime, owner, client, _, cookie, params, browser = github_login
    user, token = await session_context(settings, runtime, client, cookie)
    assert user["verified_email"] is None and token == "private-token"
    async with owner.connect() as connection:
        encrypted = await connection.scalar(text("SELECT encrypted_token FROM app.auth_sessions"))
        assert "private" not in encrypted and "private-token" in Fernet(settings.encryption_key).decrypt(encrypted.encode()).decode()
    with pytest.raises(DomainError, match="invalid_auth"):
        await complete_login(settings, runtime, client, params, browser, "")


async def test_concurrent_refresh_runs_once_and_identity_revocation_deletes_session(github_login):
    import asyncio
    import json
    import time
    from sqlalchemy import text
    from docweave.core.errors import DomainError
    from docweave.services.github_auth import session_context
    settings, runtime, owner, client, state, cookie, _, _ = github_login
    token = {"access_token": "expired", "expires_at": 1, "refresh_token": "old-refresh", "refresh_expires_at": time.time() + 600}
    encrypted = Fernet(settings.encryption_key).encrypt(json.dumps(token).encode()).decode()
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.auth_sessions SET encrypted_token=:token"), {"token": encrypted})
    await asyncio.gather(*(session_context(settings, runtime, client, cookie) for _ in range(2)))
    assert state["refreshes"] == 1
    state["identity"] = 99
    with pytest.raises(DomainError, match="unauthenticated"):
        await session_context(settings, runtime, client, cookie)
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.auth_sessions")) == 0
