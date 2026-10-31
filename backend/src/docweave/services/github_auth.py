"""Browser-bound GitHub login and serialized encrypted user-token refresh."""
import json
import secrets
import time
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from docweave.core.errors import DomainError
from docweave.core.security import digest
from docweave.repositories import auth as repository


async def begin_login(settings, engine, client, client_host, previous):
    async with engine.begin() as connection:
        await repository.expire_login_limits(connection)
        count = await repository.record_login_attempt(connection, {"bucket": digest("login:" + client_host)})
        await repository.expire_flows(connection)
        await repository.expire_sessions(connection)
    if count > 10:
        raise DomainError("rate_limited", headers={"Retry-After": "60"})
    browser, state, verifier = (secrets.token_hex(32) for _ in range(3))
    payload = Fernet(settings.encryption_key).encrypt(json.dumps({"verifier": verifier}).encode()).decode()
    async with engine.begin() as connection:
        if previous:
            await repository.delete_browser_flow(connection, {"browser": digest(previous)})
        await repository.create_flow(connection, {"state": digest(state), "browser": digest(browser), "data": payload})
    return client.authorize_url(state, verifier), browser


async def complete_login(settings, engine, client, params, browser, old):
    async with engine.begin() as connection:
        flow = await repository.consume_flow(connection, {"state": digest(params["state"]), "browser": digest(browser)})
    if not flow or not params.get("code") or "error" in params:
        raise DomainError("invalid_auth")
    try:
        saved = json.loads(Fernet(settings.encryption_key).decrypt(flow.encode()))
        token = await client.exchange_code(params["code"], saved["verifier"])
        identity = await client.user(token["access_token"])
    except (DomainError, ValueError, KeyError, InvalidToken):
        raise DomainError("invalid_auth") from None
    cookie = secrets.token_hex(32)
    encrypted = Fernet(settings.encryption_key).encrypt(json.dumps(token).encode()).decode()
    expiry = datetime.fromtimestamp(time.time() + 28800, timezone.utc)
    async with engine.begin() as connection:
        # GitHub's public profile email is optional and is not verified-email evidence.
        user_id = await repository.provision_identity(connection, {"issuer": settings.issuer, "subject": str(identity["id"]),
            "name": identity["name"], "email": None})
        if old:
            await repository.delete_session(connection, {"hash": digest(old)})
        await repository.create_session(connection, {"hash": digest(cookie), "user": user_id, "token": encrypted, "expiry": expiry})
    return cookie, 28800


async def session_context(settings, engine, client, cookie):
    """Recheck GitHub identity on every use; a row lock prevents refresh-token races."""
    if not cookie:
        raise DomainError("unauthenticated")
    invalid = False
    unavailable = None
    async with engine.begin() as connection:
        session = await repository.locked_session(connection, {"hash": digest(cookie)})
        if not session:
            raise DomainError("unauthenticated")
        await repository.set_actor(connection, {"actor": str(session["user_id"])})
        user = await repository.identity_user(connection, {"id": session["user_id"]})
        try:
            if not user or user["issuer"] != settings.issuer:
                raise DomainError("unauthenticated")
            token = json.loads(Fernet(settings.encryption_key).decrypt(session["encrypted_token"].encode()))
            if token.get("expires_at", float("inf")) <= time.time() + 60:
                if not token.get("refresh_token") or token.get("refresh_expires_at", 0) <= time.time():
                    raise DomainError("unauthenticated")
                token = await client.refresh_token(token["refresh_token"])
                encrypted = Fernet(settings.encryption_key).encrypt(json.dumps(token).encode()).decode()
                await repository.rotate_token(connection,
                    {"token": encrypted, "hash": digest(cookie)})
            identity = await client.user(token["access_token"])
            if str(identity["id"]) != user["subject"]:
                raise DomainError("unauthenticated")
        except DomainError as exc:
            if exc.code not in ("unauthenticated", "invalid_auth", "forbidden", "not_found"):
                # Persist a rotated refresh token even if the subsequent identity check is unavailable.
                unavailable = exc
            else:
                invalid = True
        except (ValueError, TypeError, KeyError, InvalidToken):
            invalid = True
        if invalid:
            await repository.delete_session(connection, {"hash": digest(cookie)})
    if invalid:
        raise DomainError("unauthenticated")
    if unavailable:
        raise unavailable
    return {"id": str(user["id"]), "display_name": user["display_name"], "verified_email": user["email"]}, token["access_token"]
