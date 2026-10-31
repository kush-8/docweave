"""Personal GitHub App authentication and repository onboarding routes."""
import hmac
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, Security
from fastapi.responses import RedirectResponse

from docweave.api.dependencies.auth import cookie_value, set_cookie, session_cookie, csrf_header
from docweave.core.security import csrf_token, digest
from docweave.repositories import auth as repository
from docweave.schemas.auth import CurrentUser
from docweave.services.github_auth import begin_login, complete_login, session_context


router = APIRouter(prefix="/api/v1", tags=["Authentication"])


def github_service(request):
    service = getattr(request.app.state, "github", None)
    if service is None:
        raise HTTPException(503)
    return service


async def require_github_user(request: Request, session_cookie_value=Security(session_cookie)):
    cookie = cookie_value(request, "docweave_session")
    if not cookie:
        raise HTTPException(401)
    settings, engine, client = github_service(request)
    user, token = await session_context(settings, engine, client, cookie)
    request.state.github_token = token
    user["csrf_token"] = csrf_token(settings, cookie)
    return user


async def require_github_csrf(request: Request, user=Depends(require_github_user), header=Security(csrf_header)):
    settings, _, _ = github_service(request)
    if request.headers.get("origin") != settings.origin or not hmac.compare_digest((header or "").encode(), user["csrf_token"].encode()):
        raise HTTPException(403)
    return user


@router.get("/auth/login", operation_id="startLogin", status_code=302)
async def start_login(request: Request):
    settings, engine, client = github_service(request)
    url, browser = await begin_login(settings, engine, client, request.client.host if request.client else "unknown",
                                     cookie_value(request, "docweave_login"))
    response = RedirectResponse(url, status_code=302)
    set_cookie(response, "docweave_login", browser, settings, 600)
    return response


@router.get("/auth/callback", operation_id="finishLogin", status_code=302)
async def finish_login(request: Request):
    settings, engine, client = github_service(request)
    params = request.query_params
    browser = cookie_value(request, "docweave_login")
    if not browser or any(len(params.getlist(key)) > 1 for key in ("state", "code", "error")) or not params.get("state"):
        raise HTTPException(400)
    cookie, max_age = await complete_login(settings, engine, client, dict(params), browser, cookie_value(request, "docweave_session"))
    response = RedirectResponse(settings.origin + "/", status_code=302)
    set_cookie(response, "docweave_session", cookie, settings, max_age)
    response.delete_cookie("docweave_login", path="/", secure=settings.secure, httponly=True, samesite="lax")
    return response


@router.get("/me", operation_id="getCurrentUser", response_model=CurrentUser)
async def current_user(user=Depends(require_github_user)):
    return user


@router.post("/auth/logout", operation_id="logout", status_code=204)
async def logout(request: Request, user=Depends(require_github_csrf)):
    settings, engine, _ = github_service(request)
    async with engine.begin() as connection:
        await repository.delete_session(connection, {"hash": digest(cookie_value(request, "docweave_session"))})
    response = Response(status_code=204)
    response.delete_cookie("docweave_session", path="/", secure=settings.secure, httponly=True, samesite="lax")
    return response


@router.get("/connections/github", operation_id="getGitHubConnection")
async def connection_status(request: Request, user=Depends(require_github_user)):
    settings, _, client = github_service(request)
    installations = await client.installations(request.state.github_token)
    return {"connected": True, "installed": any(not row["suspended"] for row in installations),
            "installations": installations, "installation_url": settings.installation_url}


@router.get("/connections/github/repositories", operation_id="listGitHubRepositories")
async def repositories(request: Request, user=Depends(require_github_user)):
    _, _, client = github_service(request)
    return {"items": await client.repositories(request.state.github_token)}


@router.get("/connections/github/repositories/{repository_id}/branches", operation_id="listGitHubBranches")
async def branches(request: Request, repository_id: int = Path(gt=0), user=Depends(require_github_user)):
    _, _, client = github_service(request)
    return {"items": await client.branches(request.state.github_token, repository_id)}
