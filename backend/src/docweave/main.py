"""Authenticated API foundation; domain feature operations remain reserved."""

import re
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from docweave.routes import FEATURE_ROUTES
from docweave.auth import AuthSettings, make_oidc, require_csrf, require_user, router
from docweave.db import make_engine
from docweave.settings import database_url
from docweave.policy import require_actor, require_owner, require_project_actor, require_collection_actor, require_collection_writer
from docweave.workspaces import router as workspace_router
from docweave.memberships import router as membership_router
from docweave.projects import router as project_router
from docweave.collections import router as collection_router
from docweave.budget import router as budget_router
from docweave.providers import router as provider_router
from docweave.ingestion import router as ingestion_router


class Health(BaseModel):
    status: Literal["ok"]


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool


ERRORS = {
    400: ("invalid_auth", "Sign-in failed. Please start sign-in again.", False),
    401: ("unauthenticated", "Sign in to continue.", False),
    403: ("csrf_failed", "The request origin or security token is invalid.", False),
    404: ("not_found", "Resource not found.", False),
    405: ("method_not_allowed", "Method not allowed.", False),
    413: ("upload_too_large", "The upload exceeds the allowed size.", False),
    422: ("invalid_request", "The request is invalid.", False),
    429: ("rate_limited", "Too many sign-in attempts. Try again shortly.", True),
    500: ("internal_error", "An internal error occurred.", False),
    501: ("not_implemented", "This operation is not implemented yet.", False),
    503: ("not_ready", "Required application services are unavailable.", True),
}


EXPECTED_ERRORS = {
    (400, "invalid_cursor"): ("invalid_cursor", "The pagination cursor is invalid.", False),
    (403, "forbidden"): ("forbidden", "You do not have permission for this operation.", False),
    (409, "last_owner"): ("last_owner", "The last workspace owner cannot be removed or demoted.", False),
    (409, "already_member"): ("already_member", "You already belong to this workspace.", False),
    (409, "revision_conflict"): ("revision_conflict", "The resource changed. Reload it before editing.", False),
    (409, "ingestion_active"): ("ingestion_active", "Another ingestion is active for this document.", True),
}


def error_response(request: Request, status: int, headers=None, detail=None) -> JSONResponse:
    code, message, retryable = EXPECTED_ERRORS.get((status, detail), ERRORS.get(status, ("http_error", "Request failed.", False)))
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id, "retryable": retryable},
        headers={**(headers or {}), "X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


async def not_implemented():
    raise HTTPException(status_code=501)


def create_app(*, auth_settings=None, auth_engine=None, oidc=None) -> FastAPI:
    settings = auth_settings or AuthSettings.load()
    engine = auth_engine or (make_engine(database_url("DATABASE_URL")) if settings else None)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if engine is not None and auth_engine is None:
            await engine.dispose()

    app = FastAPI(
        title="DocWeave API",
        version="0.1.0",
        description="Authentication, workspaces, memberships/invitations, manual projects, collection grants, processor consent, configured answer profiles, financial admission, own-tenant usage and durable TXT/Markdown preparation are implemented. Internal scoped retrieval and a recorded-vector evaluator exist. Hosted indexing, conversations and inference remain unavailable.",
        lifespan=lifespan,
    )
    app.state.auth = (settings, engine, oidc or make_oidc(settings)) if settings else None
    feature_routers = (router, workspace_router, membership_router, project_router, collection_router, budget_router, provider_router, ingestion_router)
    for feature_router in feature_routers:
        app.include_router(feature_router)
    implemented_routes = [route for feature_router in feature_routers for route in feature_router.routes]
    implemented_ids = {route.operation_id for route in implemented_routes}

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error_response(request, 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return error_response(request, exc.status_code, exc.headers, exc.detail if isinstance(exc.detail, str) else None)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error_response(request, 500)

    @app.get("/api/v1/health/live", response_model=Health, operation_id="getLiveness", tags=["Health"])
    async def liveness():
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", response_model=ApiError, status_code=503,
             operation_id="getReadiness", tags=["Health"])
    async def readiness():
        raise HTTPException(status_code=503)

    for method, path, operation_id, tag in FEATURE_ROUTES:
        if operation_id in implemented_ids:
            continue
        dependencies = [] if path in ("/catalog", "/providers") else [Depends(require_user if method == "GET" else require_csrf)]
        if path.startswith("/workspaces/{workspace_id}/"):
            owner_only = "/members" in path or "/invitations" in path or (path.endswith("/projects") and method == "POST")
            dependencies.append(Depends(require_owner if owner_only else require_actor))
        if path.startswith("/projects/{project_id}/"):
            dependencies.append(Depends(require_project_actor))
        if path.startswith("/collections/{collection_id}/"):
            dependencies.append(Depends(require_collection_actor if method == "GET" else require_collection_writer))
        app.add_api_route(
            f"/api/v1{path}",
            not_implemented,
            methods=[method],
            operation_id=operation_id,
            tags=[tag],
            status_code=501,
            response_model=ApiError,
            responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}},
            dependencies=dependencies,
            summary=f"{operation_id} (not implemented)",
            description="Reserved domain operation. Private routes enforce sessions and mutation origin/CSRF; workspace-scoped routes also enforce current membership/required owner role.",
            openapi_extra={"parameters": [
                {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
                for name in re.findall(r"\{([^}]+)\}", path)
            ], "security": [] if path in ("/catalog", "/providers") else [{"sessionCookie": [],
                **({"csrfToken": []} if method != "GET" else {})}]},
        )

    generate_openapi = app.openapi

    def openapi():
        schema = generate_openapi()
        # FastAPI appends security alternatives when merging extras; preserve cookie AND CSRF.
        for route in [*app.routes, *implemented_routes]:
            extra = getattr(route, "openapi_extra", None) or {}
            if "security" in extra:
                for method in route.methods:
                    schema["paths"][route.path][method.lower()]["security"] = extra["security"]
        return schema

    app.openapi = openapi
    return app
