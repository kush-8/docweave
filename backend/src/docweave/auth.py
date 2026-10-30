"""Keycloak owns credentials; the API issues opaque, expiring application sessions."""

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyCookie, APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import text


@dataclass(frozen=True)
class AuthSettings:
    origin: str
    issuer: str
    client_id: str
    client_secret: str = field(repr=False)
    encryption_key: str = field(repr=False)
    secure: bool
    google_enabled: bool = False
    github_enabled: bool = False

    @property
    def callback(self):
        return self.origin + "/api/v1/auth/callback"

    @classmethod
    def load(cls, values=None):
        if values is None:
            values = {**dotenv_values(Path(__file__).resolve().parents[3] / ".env"), **os.environ}
        required = ("APP_ORIGIN", "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "AUTH_ENCRYPTION_KEY")
        if not any(values.get(key) for key in required):
            return None
        try:
            if not all(isinstance(values.get(key), str) and values[key].strip() for key in required):
                raise ValueError
            for key in ("AUTH_LOCALHOST_HTTP", "OIDC_GOOGLE_ENABLED", "OIDC_GITHUB_ENABLED"):
                if values.get(key, "false") not in ("true", "false"):
                    raise ValueError
            local = values.get("AUTH_LOCALHOST_HTTP") == "true"
            for key in ("APP_ORIGIN", "OIDC_ISSUER"):
                url = urlsplit(values[key])
                if not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError
                if local and url.hostname not in ("localhost", "127.0.0.1", "::1"):
                    raise ValueError
                if url.scheme != "https" and not (local and url.scheme == "http"):
                    raise ValueError
                if key == "APP_ORIGIN" and url.path not in ("", "/"):
                    raise ValueError
                url.port  # Reject malformed ports without exposing configuration.
            origin = urlsplit(values["APP_ORIGIN"])
            host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
            port = origin.port
            authority = host if port is None or port == {"http": 80, "https": 443}[origin.scheme] else f"{host}:{port}"
            Fernet(values["AUTH_ENCRYPTION_KEY"].encode())
            return cls(f"{origin.scheme}://{authority}", values["OIDC_ISSUER"].rstrip("/"), values["OIDC_CLIENT_ID"],
                values["OIDC_CLIENT_SECRET"], values["AUTH_ENCRYPTION_KEY"], not local,
                values.get("OIDC_GOOGLE_ENABLED") == "true", values.get("OIDC_GITHUB_ENABLED") == "true")
        except (ValueError, TypeError):
            raise ValueError("Auth requires complete OIDC configuration, a Fernet key, and HTTPS or explicit loopback HTTP.") from None


def make_oidc(settings, **client_kwargs):
    return OAuth().register("keycloak", client_id=settings.client_id, client_secret=settings.client_secret,
        server_metadata_url=settings.issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256",
                       "timeout": 10, "trust_env": False, **client_kwargs})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(settings, cookie):
    return hmac.new(settings.encryption_key.encode(), ("csrf:" + cookie).encode(), hashlib.sha256).hexdigest()


def auth_service(request):
    if request.app.state.auth is None:
        raise HTTPException(503)
    return request.app.state.auth


def cookie_value(request, name):
    value = request.cookies.get(name, "")
    return value if len(value) == 64 and all(c in "0123456789abcdef" for c in value) else ""


def set_cookie(response, name, value, settings, max_age):
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=settings.secure, samesite="lax", path="/")


session_cookie = APIKeyCookie(name="docweave_session", scheme_name="sessionCookie", auto_error=False)
csrf_header = APIKeyHeader(name="X-CSRF-Token", scheme_name="csrfToken", auto_error=False)


async def require_user(request: Request, session_cookie_value=Security(session_cookie)):
    cookie = cookie_value(request, "docweave_session")
    if not cookie:
        raise HTTPException(401)
    settings, engine, _ = auth_service(request)
    async with engine.begin() as connection:
        session = (await connection.execute(text(
            "SELECT user_id FROM app.auth_sessions WHERE token_hash=:hash AND expires_at>now()"
        ), {"hash": digest(cookie)})).mappings().first()
        if not session:
            raise HTTPException(401)
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {"actor": str(session["user_id"])})
        user = (await connection.execute(text("SELECT id,display_name,email,email_verified FROM app.users WHERE id=:id"),
            {"id": session["user_id"]})).mappings().first()
        if not user or not user["email_verified"]:
            raise HTTPException(401)
    return {"id": str(user["id"]), "display_name": user["display_name"], "verified_email": user["email"],
            "csrf_token": csrf_token(settings, cookie)}


async def require_csrf(request: Request, user=Depends(require_user), header=Security(csrf_header)):
    settings, _, _ = auth_service(request)
    if request.headers.get("origin") != settings.origin or not hmac.compare_digest(
        (header or "").encode(), user["csrf_token"].encode()
    ):
        raise HTTPException(403)
    return user


class CurrentUser(BaseModel):
    id: str
    display_name: str
    verified_email: str
    csrf_token: str


router = APIRouter(prefix="/api/v1", tags=["Authentication"])


@router.get("/auth/login", operation_id="startLogin", status_code=302,
    responses={422: {"description": "Invalid login method."}, 429: {"description": "Login rate limit exceeded."},
               503: {"description": "Authentication service or selected broker is unavailable."}})
async def start_login(request: Request, method: Literal["email", "google", "github"]):
    settings, engine, oidc = auth_service(request)
    if method != "email" and not getattr(settings, method + "_enabled"):
        raise HTTPException(503)
    # Socket peers are authoritative; deployment proxies must be separately trusted.
    bucket = digest("login:" + (request.client.host if request.client else "unknown"))
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM app.auth_rate_limits WHERE resets_at<=now()"))
        count = await connection.scalar(text("""
            INSERT INTO app.auth_rate_limits(bucket,attempts,resets_at) VALUES (:bucket,1,now()+interval '60 seconds')
            ON CONFLICT (bucket) DO UPDATE SET attempts=app.auth_rate_limits.attempts+1 RETURNING attempts
        """), {"bucket": bucket})
        await connection.execute(text("DELETE FROM app.auth_flows WHERE expires_at<=now()"))
        await connection.execute(text("DELETE FROM app.auth_sessions WHERE expires_at<=now()"))
    if count > 10:
        raise HTTPException(429, headers={"Retry-After": "60"})
    browser, state, nonce, verifier = (secrets.token_hex(32) for _ in range(4))
    try:
        metadata = await oidc.load_server_metadata()
        if metadata.get("issuer") != settings.issuer:
            raise ValueError
        authorization = await oidc.create_authorization_url(settings.callback, state=state, nonce=nonce,
            code_verifier=verifier, kc_idp_hint="" if method == "email" else method, prompt="login")
    except Exception:
        raise HTTPException(503) from None
    payload = Fernet(settings.encryption_key).encrypt(json.dumps({"nonce": nonce, "verifier": verifier}).encode()).decode()
    async with engine.begin() as connection:
        previous = cookie_value(request, "docweave_login")
        if previous:
            await connection.execute(text("DELETE FROM app.auth_flows WHERE browser_hash=:browser"), {"browser": digest(previous)})
        await connection.execute(text("""
            INSERT INTO app.auth_flows(state_hash,browser_hash,encrypted_data,expires_at)
            VALUES (:state,:browser,:data,now()+interval '10 minutes')
        """), {"state": digest(state), "browser": digest(browser), "data": payload})
    response = RedirectResponse(authorization["url"], status_code=302)
    set_cookie(response, "docweave_login", browser, settings, 600)
    return response


@router.get("/auth/callback", operation_id="finishLogin", status_code=302,
    responses={400: {"description": "Invalid, denied, expired or consumed sign-in transaction."},
               503: {"description": "Authentication is not configured."}})
async def finish_login(request: Request):
    settings, engine, oidc = auth_service(request)
    params = request.query_params
    browser = cookie_value(request, "docweave_login")
    if not browser or any(len(params.getlist(key)) > 1 for key in ("state", "code", "error")) or not params.get("state"):
        raise HTTPException(400)
    async with engine.begin() as connection:
        flow = await connection.scalar(text("""
            DELETE FROM app.auth_flows WHERE state_hash=:state AND browser_hash=:browser AND expires_at>now()
            RETURNING encrypted_data
        """), {"state": digest(params["state"]), "browser": digest(browser)})
    if not flow or not params.get("code") or "error" in params:
        raise HTTPException(400)
    try:
        saved = json.loads(Fernet(settings.encryption_key).decrypt(flow.encode()))
        token = await oidc.fetch_access_token(redirect_uri=settings.callback, code=params["code"], code_verifier=saved["verifier"])
        metadata = await oidc.load_server_metadata()
        if metadata.get("issuer") != settings.issuer:
            raise ValueError
        metadata["id_token_signing_alg_values_supported"] = ["RS256"]
        claims = await oidc.parse_id_token(token, nonce=saved["nonce"], leeway=0,
            claims_options={"iss": {"essential": True, "value": settings.issuer},
                            "aud": {"essential": True, "value": settings.client_id}})
        if not claims or claims.get("email_verified") is not True or not all(
            isinstance(claims.get(key), str) and claims[key].strip() for key in ("sub", "email")
        ) or claims.get("azp", settings.client_id) != settings.client_id:
            raise ValueError
        now = datetime.now(timezone.utc).timestamp()
        expires = min(now + 28800, float(claims["exp"]), float(token["expires_at"]))
        if expires <= now or not token.get("access_token"):
            raise ValueError
    except Exception:
        raise HTTPException(400) from None
    cookie = secrets.token_hex(32)
    encrypted = Fernet(settings.encryption_key).encrypt(json.dumps(token).encode()).decode()
    async with engine.begin() as connection:
        user_id = await connection.scalar(text("SELECT app.provision_identity(:issuer,:subject,:name,:email)"),
            {"issuer": settings.issuer, "subject": claims["sub"], "name": claims.get("name") or claims["email"], "email": claims["email"]})
        old = cookie_value(request, "docweave_session")
        if old:
            await connection.execute(text("DELETE FROM app.auth_sessions WHERE token_hash=:hash"), {"hash": digest(old)})
        await connection.execute(text("""
            INSERT INTO app.auth_sessions(token_hash,user_id,encrypted_token,expires_at) VALUES (:hash,:user,:token,:expiry)
        """), {"hash": digest(cookie), "user": user_id, "token": encrypted, "expiry": datetime.fromtimestamp(expires, timezone.utc)})
    response = RedirectResponse(settings.origin + "/", status_code=302)
    set_cookie(response, "docweave_session", cookie, settings, max(1, int(expires-now)))
    response.delete_cookie("docweave_login", path="/", secure=settings.secure, httponly=True, samesite="lax")
    return response


@router.get("/me", operation_id="getCurrentUser", response_model=CurrentUser,
    responses={401: {"description": "Missing or expired session."}, 503: {"description": "Authentication is unavailable."}})
async def current_user(user=Depends(require_user)):
    return user


@router.post("/auth/logout", operation_id="logout", status_code=204,
    responses={401: {"description": "Missing or expired session."}, 403: {"description": "Invalid origin or CSRF token."}},
    openapi_extra={"security": [{"sessionCookie": [], "csrfToken": []}]})
async def logout(request: Request, user=Depends(require_csrf)):
    settings, engine, _ = auth_service(request)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM app.auth_sessions WHERE token_hash=:hash"),
            {"hash": digest(cookie_value(request, "docweave_session"))})
    response = Response(status_code=204)
    response.delete_cookie("docweave_session", path="/", secure=settings.secure, httponly=True, samesite="lax")
    return response
