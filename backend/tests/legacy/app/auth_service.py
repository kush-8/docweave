import json, secrets
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from docweave.core.errors import DomainError
from docweave.core.security import digest
from docweave.repositories import auth as repository


async def begin_login(settings, engine, oidc, method, client_host, previous):
    if method != "email" and not getattr(settings, method + "_enabled"):
        raise DomainError("not_ready")
    # Socket peers are authoritative; deployment proxies must be separately trusted.
    bucket = digest("login:" + client_host)
    async with engine.begin() as connection:
        await repository.expire_login_limits(connection)
        count = await repository.record_login_attempt(connection, {"bucket": bucket})
        await repository.expire_flows(connection)
        await repository.expire_sessions(connection)
    if count > 10:
        raise DomainError("rate_limited", headers={"Retry-After": "60"})
    browser, state, nonce, verifier = (secrets.token_hex(32) for _ in range(4))
    try:
        metadata = await oidc.load_server_metadata()
        if metadata.get("issuer") != settings.issuer:
            raise ValueError
        authorization = await oidc.create_authorization_url(settings.callback, state=state, nonce=nonce,
            code_verifier=verifier, kc_idp_hint="" if method == "email" else method, prompt="login")
    except Exception:
        raise DomainError("not_ready") from None
    payload = Fernet(settings.encryption_key).encrypt(json.dumps({"nonce": nonce, "verifier": verifier}).encode()).decode()
    async with engine.begin() as connection:
        if previous:
            await repository.delete_browser_flow(connection, {"browser": digest(previous)})
        await repository.create_flow(connection, {"state": digest(state), "browser": digest(browser), "data": payload})
    return authorization["url"], browser


async def complete_login(settings, engine, oidc, params, browser, old):
    async with engine.begin() as connection:
        flow = await repository.consume_flow(connection, {"state": digest(params["state"]), "browser": digest(browser)})
    if not flow or not params.get("code") or "error" in params:
        raise DomainError("invalid_auth")
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
        raise DomainError("invalid_auth") from None
    cookie = secrets.token_hex(32)
    encrypted = Fernet(settings.encryption_key).encrypt(json.dumps(token).encode()).decode()
    async with engine.begin() as connection:
        user_id = await repository.provision_identity(connection, {"issuer": settings.issuer, "subject": claims["sub"], "name": claims.get("name") or claims["email"], "email": claims["email"]})
        if old:
            await repository.delete_session(connection, {"hash": digest(old)})
        await repository.create_session(connection, {"hash": digest(cookie), "user": user_id, "token": encrypted, "expiry": datetime.fromtimestamp(expires, timezone.utc)})
    return cookie, max(1, int(expires-now))
