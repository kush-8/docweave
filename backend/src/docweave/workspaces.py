"""Own-workspace navigation and atomic first-owner creation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from docweave.auth import auth_service, require_csrf, require_user
from docweave.db import tenant_session
from docweave.pagination import decode_cursor, page


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, pattern=r"^[^\x00]+$", description="Trimmed, nonblank name without NUL characters.")


class WorkspaceView(BaseModel):
    id: UUID
    name: str
    role: Literal["owner", "maintainer", "member"]
    created_at: datetime


class WorkspacePage(BaseModel):
    items: list[WorkspaceView]
    next_cursor: str | None


router = APIRouter(prefix="/api/v1", tags=["Workspaces"])


@router.post("/workspaces", operation_id="createWorkspace", status_code=201, response_model=WorkspaceView,
    responses={401: {"description": "Sign in required."}, 403: {"description": "Invalid origin or CSRF token."},
               422: {"description": "A nonblank name is required; extra fields are rejected."}},
    openapi_extra={"security": [{"sessionCookie": [], "csrfToken": []}]})
async def create_workspace(body: WorkspaceCreate, request: Request, user=Depends(require_csrf)):
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        result = await session.execute(text("SELECT * FROM app.create_workspace(:name)"), {"name": body.name})
        workspace = dict(result.mappings().one())
    return workspace


@router.get("/workspaces", operation_id="listWorkspaces", response_model=WorkspacePage,
    responses={400: {"description": "Invalid or other-actor cursor."}, 401: {"description": "Sign in required."},
               422: {"description": "Invalid pagination bounds."}})
async def list_workspaces(request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), user=Depends(require_user)):
    settings, engine, _ = auth_service(request)
    after, after_id = decode_cursor(settings, cursor, user["id"], "workspaces:v1")
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        result = await session.execute(text("SELECT * FROM app.list_workspaces(:after,:id,:limit)"),
            {"after": after, "id": after_id, "limit": limit + 1})
        workspaces = [dict(row) for row in result.mappings()]
    return page(settings, workspaces, limit, user["id"], "workspaces:v1")
