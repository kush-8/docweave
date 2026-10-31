import hmac
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyCookie, APIKeyHeader
from docweave.repositories import auth as repository
from docweave.core.security import digest, csrf_token


session_cookie = APIKeyCookie(name="docweave_session", scheme_name="sessionCookie", auto_error=False)
csrf_header = APIKeyHeader(name="X-CSRF-Token", scheme_name="csrfToken", auto_error=False)

def auth_service(request):
    if request.app.state.auth is None:
        raise HTTPException(503)
    return request.app.state.auth


def cookie_value(request, name):
    value = request.cookies.get(name, "")
    return value if len(value) == 64 and all(c in "0123456789abcdef" for c in value) else ""


def set_cookie(response, name, value, settings, max_age):
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=settings.secure, samesite="lax", path="/")


async def require_user(request: Request, session_cookie_value=Security(session_cookie)):
    cookie = cookie_value(request, "docweave_session")
    if not cookie:
        raise HTTPException(401)
    settings, engine, _ = auth_service(request)
    async with engine.begin() as connection:
        session = (await repository.session_user(connection, {"hash": digest(cookie)})).mappings().first()
        if not session:
            raise HTTPException(401)
        await repository.set_actor(connection, {"actor": str(session["user_id"])})
        user = (await repository.load_user(connection, {"id": session["user_id"]})).mappings().first()
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
