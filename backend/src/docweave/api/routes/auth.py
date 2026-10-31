from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from docweave.repositories import auth as repository
from docweave.schemas.auth import CurrentUser
from docweave.api.dependencies.auth import auth_service, require_user, require_csrf, cookie_value, set_cookie
from docweave.services.auth import begin_login, complete_login
from docweave.core.security import digest


router = APIRouter(prefix="/api/v1", tags=["Authentication"])


@router.get("/auth/login", operation_id="startLogin", status_code=302,
    responses={422: {"description": "Invalid login method."}, 429: {"description": "Login rate limit exceeded."},
               503: {"description": "Authentication service or selected broker is unavailable."}})
async def start_login(request: Request, method: Literal["email", "google", "github"]):
    settings, engine, oidc = auth_service(request)
    url, browser = await begin_login(settings, engine, oidc, method,
        request.client.host if request.client else "unknown", cookie_value(request, "docweave_login"))
    response = RedirectResponse(url, status_code=302)
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
    cookie, max_age = await complete_login(settings, engine, oidc, dict(params), browser, cookie_value(request, "docweave_session"))
    response = RedirectResponse(settings.origin + "/", status_code=302)
    set_cookie(response, "docweave_session", cookie, settings, max_age)
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
        await repository.delete_session(connection, {"hash": digest(cookie_value(request, "docweave_session"))})
    response = Response(status_code=204)
    response.delete_cookie("docweave_session", path="/", secure=settings.secure, httponly=True, samesite="lax")
    return response
