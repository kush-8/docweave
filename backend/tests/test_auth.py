"""Real signed OIDC tokens and restricted-role PostgreSQL exercise auth boundaries."""

import time
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from joserfc import jwt
from joserfc.jwk import RSAKey
from sqlalchemy import text

from test_database import databases
from test_database import test_urls  # noqa: F401 -- isolated DB fixtures

pytestmark = pytest.mark.anyio
ORIGIN = "https://app.example.test"
ISSUER = "https://identity.example.test/realms/docweave"


def configuration(**overrides):
    return {"APP_ORIGIN": ORIGIN, "OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": "docweave",
        "OIDC_CLIENT_SECRET": "test-secret", "AUTH_ENCRYPTION_KEY": Fernet.generate_key().decode(), **overrides}


@pytest.mark.parametrize("overrides", [
    {"APP_ORIGIN": "http://app.example.test"},
    {"APP_ORIGIN": "http://app.example.test", "AUTH_LOCALHOST_HTTP": "true"},
    {"APP_ORIGIN": ORIGIN + "/path"}, {"APP_ORIGIN": "https://user:pass@app.example.test"},
    {"OIDC_ISSUER": "http://identity.example.test"}, {"OIDC_ISSUER": ISSUER + "?x=1"},
    {"OIDC_CLIENT_SECRET": ""}, {"AUTH_ENCRYPTION_KEY": "bad-key"},
    {"AUTH_LOCALHOST_HTTP": "yes"}, {"AUTH_LOCALHOST_HTTP": "true"},
])
async def test_unsafe_auth_configuration_is_rejected(overrides):
    from docweave.core.settings import AuthSettings
    with pytest.raises(ValueError):
        AuthSettings.load(configuration(**overrides))


@pytest.mark.parametrize("origin", ["https://APP.EXAMPLE.TEST", ORIGIN + ":443/"])
async def test_origin_matches_browser_serialization(origin):
    from docweave.core.settings import AuthSettings
    assert AuthSettings.load(configuration(APP_ORIGIN=origin)).origin == ORIGIN


async def test_local_http_requires_explicit_loopback_configuration():
    from docweave.core.settings import AuthSettings
    settings = AuthSettings.load(configuration(APP_ORIGIN="http://127.0.0.1:5173",
        OIDC_ISSUER="http://127.0.0.1:58080/realms/docweave", AUTH_LOCALHOST_HTTP="true"))
    assert not settings.secure
    assert settings.callback == "http://127.0.0.1:5173/api/v1/auth/callback"


@pytest.fixture
async def auth_client(databases):
    import httpx2
    from docweave.core.settings import AuthSettings
    from docweave.integrations.oidc import make_oidc
    from docweave.main import create_app

    owner, runtime = databases
    key = RSAKey.generate_key(2048)
    key.ensure_kid()
    data = {"nonce": "", "claims": {}, "exchanges": [], "token_error": False, "wrong_key": False}
    settings = AuthSettings.load(configuration(OIDC_GOOGLE_ENABLED="true", OIDC_GITHUB_ENABLED="true"))

    async def provider(request):
        if not request.url.path.endswith("/token"):
            raise AssertionError("Unexpected identity request")
        data["exchanges"].append(parse_qs(request.content.decode()))
        if data["token_error"]:
            return httpx2.Response(400, json={"error": "invalid_grant", "error_description": "private-marker"})
        claims = {"iss": ISSUER, "sub": "new-user", "aud": "docweave", "iat": int(time.time()),
            "exp": int(time.time()) + 300, "nonce": data["nonce"], "email_verified": True,
            "email": "person@example.test", "name": "Person", **data["claims"]}
        signing_key = RSAKey.generate_key(2048) if data["wrong_key"] else key
        encoded = jwt.encode({"alg": "RS256", "kid": key.kid}, claims, signing_key)
        return httpx2.Response(200, json={"access_token": "private-access-token", "token_type": "Bearer",
            "expires_in": 300, "id_token": encoded})

    oidc = make_oidc(settings, transport=httpx2.MockTransport(provider))
    oidc.server_metadata.update(issuer=ISSUER, authorization_endpoint=ISSUER + "/auth", token_endpoint=ISSUER + "/token",
        jwks={"keys": [key.as_dict(private=False)]}, id_token_signing_alg_values_supported=["RS256"], _loaded_at=time.time())
    app = create_app(auth_settings=settings, auth_engine=runtime, oidc=oidc)
    data["app"] = app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN) as client:
        yield client, data, owner, settings


async def begin(client, data, method="email"):
    response = await client.get("/api/v1/auth/login", params={"method": method})
    assert response.status_code == 302, response.text
    params = parse_qs(urlsplit(response.headers["location"]).query)
    data["nonce"] = params["nonce"][0]
    return response, params


async def login(client, data):
    _, params = await begin(client, data)
    return await client.get("/api/v1/auth/callback", params={"code": "code", "state": params["state"][0]})


async def test_pkce_state_and_cookie_do_not_expose_protocol_secrets(auth_client):
    client, data, _, _ = auth_client
    response, params = await begin(client, data)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [ORIGIN + "/api/v1/auth/callback"]
    cookie = response.headers["set-cookie"]
    assert all(value in cookie for value in ("HttpOnly", "Secure", "SameSite=lax"))
    assert data["nonce"] not in cookie and "code_verifier" not in cookie


@pytest.mark.parametrize("method", ["google", "github"])
async def test_broker_method_is_allowlisted(auth_client, method):
    client, data, _, _ = auth_client
    _, params = await begin(client, data, method)
    assert params["kc_idp_hint"] == [method]
    assert (await client.get("/api/v1/auth/login?method=evil")).status_code == 422


async def test_verified_identity_and_encrypted_session_work_without_membership(auth_client):
    client, data, owner, settings = auth_client
    response = await login(client, data)
    assert response.status_code == 302, response.text
    assert response.headers["location"] == ORIGIN + "/"
    assert data["exchanges"][0]["code_verifier"]
    me = await client.get("/api/v1/me")
    assert me.status_code == 200, me.text
    assert me.json()["verified_email"] == "person@example.test"
    assert me.json()["csrf_token"]
    assert "private-access-token" not in me.text
    assert me.headers["cache-control"] == "no-store"
    async with owner.connect() as connection:
        row = (await connection.execute(text("SELECT token_hash,encrypted_token FROM app.auth_sessions"))).one()
        assert client.cookies["docweave_session"] not in str(row)
        assert "private-access-token" not in str(row)
        assert b"private-access-token" in Fernet(settings.encryption_key).decrypt(row.encrypted_token.encode())
        assert (await connection.scalar(text("SELECT count(*) FROM app.memberships"))) == 2


@pytest.mark.parametrize("claims", [
    {"iss": "https://evil.test"}, {"aud": "wrong"}, {"nonce": "wrong"}, {"exp": 1},
    {"email_verified": False}, {"email_verified": "true"}, {"sub": ""}, {"email": ""}, {"azp": "wrong"},
])
async def test_invalid_claims_never_establish_a_session(auth_client, claims):
    client, data, _, _ = auth_client
    data["claims"] = claims
    assert (await login(client, data)).status_code == 400
    assert "docweave_session" not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_wrong_signature_and_token_exchange_errors_are_safe(auth_client):
    client, data, _, _ = auth_client
    data["wrong_key"] = True
    assert (await login(client, data)).status_code == 400
    data["token_error"] = True
    response = await login(client, data)
    assert response.status_code == 400
    assert "private-marker" not in response.text
    assert "docweave_session" not in client.cookies


async def test_callback_is_browser_bound_single_use_and_expires(auth_client):
    client, data, owner, _ = auth_client
    _, params = await begin(client, data)
    query = {"state": params["state"][0], "code": "code"}
    cookie = client.cookies["docweave_login"]
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/callback", params=query)).status_code == 400
    client.cookies.set("docweave_login", cookie)
    assert (await client.get("/api/v1/auth/callback", params=query)).status_code == 302
    assert (await client.get("/api/v1/auth/callback", params=query)).status_code == 400
    _, params = await begin(client, data)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.auth_flows SET expires_at=now()-interval '1 second'"))
    assert (await client.get("/api/v1/auth/callback", params={"code": "code", "state": params["state"][0]})).status_code == 400
    assert len(data["exchanges"]) == 1


async def test_callback_denial_consumes_state_without_echoing_private_error(auth_client):
    client, data, _, _ = auth_client
    _, params = await begin(client, data)
    query = {"state": params["state"][0], "error": "access_denied", "error_description": "private-marker"}
    response = await client.get("/api/v1/auth/callback", params=query)
    assert response.status_code == 400 and "private-marker" not in response.text
    assert not data["exchanges"]


async def test_logout_requires_origin_csrf_and_revokes_the_cookie(auth_client):
    client, data, _, _ = auth_client
    await login(client, data)
    cookie = client.cookies["docweave_session"]
    csrf = (await client.get("/api/v1/me")).json()["csrf_token"]
    for headers in ({}, {"Origin": ORIGIN}, {"Origin": "https://evil.test", "X-CSRF-Token": csrf},
        {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, [(b"origin", ORIGIN.encode()), (b"x-csrf-token", b"\xe9")]):
        assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 403
    response = await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
    client.cookies.set("docweave_session", cookie)
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_rotation_expiry_and_same_email_do_not_merge_accounts(auth_client):
    client, data, owner, _ = auth_client
    await login(client, data)
    old = client.cookies["docweave_session"]
    first = (await client.get("/api/v1/me")).json()
    data["claims"] = {"sub": "other-person"}
    await login(client, data)
    second = (await client.get("/api/v1/me")).json()
    assert first["id"] != second["id"] and first["csrf_token"] != second["csrf_token"]
    client.cookies.clear()
    client.cookies.set("docweave_session", old)
    assert (await client.get("/api/v1/me")).status_code == 401
    await login(client, data)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.auth_sessions SET expires_at=now()-interval '1 second'"))
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_private_stubs_and_shared_login_rate_limit(auth_client):
    client, data, _, _ = auth_client
    assert (await client.get("/api/v1/workspaces")).status_code == 401
    await login(client, data)
    assert (await client.get("/api/v1/workspaces")).status_code == 200
    assert (await client.post("/api/v1/workspaces", json={"name": "private"})).status_code == 403
    for _ in range(9):
        await begin(client, data)
    response = await client.get("/api/v1/auth/login?method=email")
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


async def test_auth_migration_matches_models_and_provisioning_has_no_public_grant(databases):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from docweave.db.models import Base

    owner, _ = databases
    async with owner.connect() as connection:
        def compare(sync):
            context = MigrationContext.configure(sync, opts={"include_schemas": True, "version_table_schema": "app",
                "include_name": lambda name, kind, parents: kind != "schema" or name != "queue"})
            return compare_metadata(context, Base.metadata)
        assert await connection.run_sync(compare) == []
        row = (await connection.execute(text("""
            SELECT prosecdef,proconfig,NOT EXISTS (
                SELECT 1 FROM aclexplode(coalesce(proacl,acldefault('f',proowner))) a
                WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
            ) AS no_public FROM pg_proc WHERE oid='app.provision_identity(text,text,text,text)'::regprocedure
        """))).one()
        assert row.prosecdef and row.no_public
        assert row.proconfig == ["search_path=pg_catalog, app"]
