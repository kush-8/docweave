"""Manual project context; documentation requests remain local until source approval."""

import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from docweave.auth import auth_service, require_csrf
from docweave.memberships import MUTATION, membership_session
from docweave.pagination import decode_cursor, page
from docweave.policy import require_actor, require_owner, require_project_actor, require_project_owner

Nonblank = Annotated[str, Field(min_length=1, pattern=r"^[^\x00]*[^\s\x00][^\x00]*$")]
ContextText = Annotated[str, Field(pattern=r"^[^\x00]*$")]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        # Omission is allowed for optional inputs; explicit null is rejected below.
        for field in schema.get("properties", {}).values():
            if "anyOf" in field:
                field["anyOf"] = [variant for variant in field["anyOf"] if variant.get("type") != "null"]
                field.pop("default", None)
        return schema

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("Omit optional fields instead of sending null.")
        return value


class StackEntry(StrictInput):
    technology: Nonblank
    docs_target: Nonblank | None = None


class ProjectCreate(StrictInput):
    model_config = ConfigDict(json_schema_extra={"oneOf": [
        {"required": ["stack"], "not": {"required": ["stack_review_id"]}},
        {"required": ["stack_review_id"], "not": {"required": ["stack"]}},
    ]})
    name: Nonblank
    goal: Nonblank
    stack: list[StackEntry] | None = Field(None, min_length=1)
    stack_review_id: UUID | None = None
    architecture_notes: ContextText = ""
    environment: ContextText = ""
    constraints: ContextText = ""

    @model_validator(mode="after")
    def one_stack(self):
        if (self.stack is None) == (self.stack_review_id is None):
            raise ValueError("Provide exactly one manual stack or confirmed review.")
        return self


class ProjectPatch(StrictInput):
    model_config = ConfigDict(json_schema_extra={"minProperties": 2})
    expected_revision: int = Field(ge=1, le=2147483647, strict=True)
    name: Nonblank | None = None
    goal: Nonblank | None = None
    stack: list[StackEntry] | None = Field(None, min_length=1)
    architecture_notes: ContextText | None = None
    environment: ContextText | None = None
    constraints: ContextText | None = None

    @model_validator(mode="after")
    def has_change(self):
        if len(self.model_fields_set) < 2:
            raise ValueError("Provide at least one field to edit.")
        return self


class ProjectDependency(BaseModel):
    id: UUID
    technology: str
    declared_version: str | None
    resolved_version: str | None
    docs_target: str | None


class ProjectView(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    goal: str
    stack: list[ProjectDependency]
    context_revision: int
    default_collection_id: UUID
    # shortcut: derive live source status when source approval/import workers are implemented.
    source_state: Literal["pending_review"]
    architecture_notes: str
    environment: str
    constraints: str


class ProjectCreated(BaseModel):
    project: ProjectView
    job_ids: list[UUID]
    pending_dependency_ids: list[UUID]


class ProjectPage(BaseModel):
    items: list[ProjectView]
    next_cursor: str | None


def context_payload(body):
    context = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision", "stack_review_id"})
    if "stack" in context:
        context["stack"] = [{"id": str(uuid4()), "technology": dep.technology, "declared_version": None,
            "resolved_version": None, "docs_target": dep.docs_target} for dep in body.stack]
    return json.dumps(context)


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
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        project = await session.scalar(text("SELECT app.create_project(CAST(:context AS jsonb))"), {"context": context_payload(body)})
    return {"project": project, "job_ids": [], "pending_dependency_ids": [dep["id"] for dep in project["stack"]]}


@router.get("/workspaces/{workspace_id}/projects", operation_id="listProjects", response_model=ProjectPage)
async def list_projects(workspace_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_actor)):
    settings, _, _ = auth_service(request)
    resource = f"projects:{actor.workspace_id}:v1"
    after, after_id = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        result = await session.execute(text("""
            SELECT p.id,p.created_at,app.project_view(p.id) AS project FROM app.projects p
            WHERE (CAST(:after AS timestamptz) IS NULL OR (p.created_at,p.id)>(:after,:id))
            ORDER BY p.created_at,p.id LIMIT :limit
        """), {"after": after, "id": after_id, "limit": limit + 1})
        rows = [dict(row) for row in result.mappings()]
    result_page = page(settings, rows, limit, actor.user_id, resource)
    return {"items": [row["project"] for row in result_page["items"]], "next_cursor": result_page["next_cursor"]}


@router.get("/projects/{project_id}", operation_id="getProject", response_model=ProjectView)
async def get_project(project_id: UUID, request: Request, actor=Depends(require_project_actor)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        project = await session.scalar(text("SELECT app.project_view(:project)"), {"project": project_id})
    if project is None:
        raise HTTPException(404)
    return project


@router.patch("/projects/{project_id}", operation_id="updateProject", response_model=ProjectView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION,
    responses={409: {"description": "The project revision changed; reload before editing."}})
async def update_project(project_id: UUID, body: ProjectPatch, request: Request, actor=Depends(require_project_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.update_project(:project,:revision,CAST(:context AS jsonb))"),
            {"project": project_id, "revision": body.expected_revision, "context": context_payload(body)})
