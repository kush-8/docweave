import re
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from docweave.api.reserved import FEATURE_ROUTES
from docweave.core.settings import AuthSettings, database_url
from docweave.integrations.oidc import make_oidc
from docweave.api.dependencies.auth import require_csrf, require_user
from docweave.api.routes.auth import router
from docweave.db.engine import make_engine
from docweave.api.dependencies.policy import require_actor, require_owner, require_project_actor, require_collection_actor, require_collection_writer
from docweave.api.routes.workspaces import router as workspace_router
from docweave.api.routes.memberships import router as membership_router
from docweave.api.routes.projects import router as project_router
from docweave.api.routes.collections import router as collection_router
from docweave.api.routes.budget import router as budget_router
from docweave.api.routes.providers import router as provider_router
from docweave.api.routes.ingestion import router as ingestion_router
from docweave.api.errors import install_error_handlers
from docweave.api.middleware import install_middleware
from docweave.schemas.health import ApiError
from docweave.api.routes.health import router as health_router


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

    install_middleware(app)

    install_error_handlers(app)

    app.include_router(health_router)

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
