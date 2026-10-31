from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from docweave.api.dependencies.auth import auth_service, require_csrf
from docweave.api.security import MUTATION
from docweave.core.pagination import decode_cursor, page
from docweave.api.dependencies.policy import require_actor, require_owner, require_project_actor, require_project_owner
from docweave.repositories import projects as repository
from docweave.schemas.projects import ProjectCreate, ProjectPatch, ProjectView, ProjectCreated, ProjectPage
from docweave.db.sessions import domain_session
from docweave.services.projects import context_payload


router = APIRouter(prefix="/api/v1", tags=["Projects"], responses={
    400: {"description": "Invalid cursor."}, 401: {"description": "Sign in required."},
    403: {"description": "Invalid origin/CSRF or insufficient workspace role."},
    404: {"description": "Project/workspace is missing or inaccessible."},
    422: {"description": "Invalid project context."},
})


@router.post("/workspaces/{workspace_id}/projects", operation_id="createProject", status_code=201,
    response_model=ProjectCreated, dependencies=[Depends(require_csrf)], openapi_extra=MUTATION,
    responses={501: {"description": "GitHub reviewed-stack creation is not implemented."}},
    description="Creates manual context, an owner-only default collection and pending documentation requests atomically. No approved source catalog/import workers exist yet; job_ids is empty and source_state is pending_review.")
async def create_project(workspace_id: UUID, body: ProjectCreate, request: Request, actor=Depends(require_owner)):
    if body.stack_review_id is not None:
        raise HTTPException(501)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        project = await repository.create_project(session, {"context": context_payload(body)})
    return {"project": project, "job_ids": [], "pending_dependency_ids": [dep["id"] for dep in project["stack"]]}


@router.get("/workspaces/{workspace_id}/projects", operation_id="listProjects", response_model=ProjectPage)
async def list_projects(workspace_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_actor)):
    settings, _, _ = auth_service(request)
    resource = f"projects:{actor.workspace_id}:v1"
    after, after_id = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        result = await repository.list_projects(session, {"after": after, "id": after_id, "limit": limit + 1})
        rows = [dict(row) for row in result.mappings()]
    result_page = page(settings, rows, limit, actor.user_id, resource)
    return {"items": [row["project"] for row in result_page["items"]], "next_cursor": result_page["next_cursor"]}


@router.get("/projects/{project_id}", operation_id="getProject", response_model=ProjectView)
async def get_project(project_id: UUID, request: Request, actor=Depends(require_project_actor)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        project = await repository.get_project(session, {"project": project_id})
    if project is None:
        raise HTTPException(404)
    return project


@router.patch("/projects/{project_id}", operation_id="updateProject", response_model=ProjectView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION,
    responses={409: {"description": "The project revision changed; reload before editing."}})
async def update_project(project_id: UUID, body: ProjectPatch, request: Request, actor=Depends(require_project_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.update_project(session, {"project": project_id, "revision": body.expected_revision, "context": context_payload(body)})
