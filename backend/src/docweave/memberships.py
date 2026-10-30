"""Owner management and single-use invitations with authority rechecked inside SQL."""

import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from docweave.auth import auth_service, digest, require_csrf
from docweave.db import tenant_session
from docweave.pagination import decode_cursor, page
from docweave.policy import require_owner

Role = Literal["owner", "maintainer", "member"]
MUTATION = {"security": [{"sessionCookie": [], "csrfToken": []}]}


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class InvitationInput(MemberRole):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def address_only(cls, value):
        if isinstance(value, str) and ("<" in value or ">" in value):
            raise ValueError("Use an email address without a display name.")
        return value


class MemberView(BaseModel):
    workspace_id: UUID
    user_id: UUID
    role: Role
    display_name: str


class InvitationView(BaseModel):
    id: UUID
    workspace_id: UUID
    email: EmailStr
    role: Role
    expires_at: datetime
    status: Literal["pending", "accepted", "expired", "revoked"]


class InvitationCreated(BaseModel):
    invitation: InvitationView
    acceptance_url: str


class MemberPage(BaseModel):
    items: list[MemberView]
    next_cursor: str | None


class InvitationPage(BaseModel):
    items: list[InvitationView]
    next_cursor: str | None


@asynccontextmanager
async def membership_session(request, actor_id, workspace_id=None):
    _, engine, _ = auth_service(request)
    try:
        async with tenant_session(engine, actor_id=actor_id, workspace_id=workspace_id) as session:
            yield session
    except DBAPIError as error:
        mapped = {"P0002": (404, None), "42501": (403, "forbidden"), "DW001": (409, "last_owner"),
                  "DW002": (409, "already_member"), "22023": (422, None)}.get(getattr(error.orig, "sqlstate", None))
        if mapped:
            raise HTTPException(mapped[0], detail=mapped[1]) from None
        raise


router = APIRouter(prefix="/api/v1", tags=["Workspaces"], responses={
    400: {"description": "Invalid cursor."}, 401: {"description": "Sign in required."},
    403: {"description": "Invalid origin/CSRF or insufficient workspace role."},
    404: {"description": "Resource is missing or inaccessible."},
    409: {"description": "Last-owner protection or already a workspace member."},
    422: {"description": "Invalid input."},
})

_LIST_SQL = {
    "members": text("SELECT * FROM app.list_members(:after,:id,:limit)"),
    "invitations": text("SELECT * FROM app.list_invitations(:after,:id,:limit)"),
}


async def owner_page(request, actor, kind, limit, cursor):
    settings, _, _ = auth_service(request)
    resource = f"{kind}:{actor.workspace_id}:v1"
    after, after_id = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(_LIST_SQL[kind], {"after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.get("/workspaces/{workspace_id}/members", operation_id="listMembers", response_model=MemberPage)
async def list_members(workspace_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_owner)):
    return await owner_page(request, actor, "members", limit, cursor)


@router.patch("/workspaces/{workspace_id}/members/{user_id}", operation_id="updateMemberRole", response_model=MemberView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def update_member(workspace_id: UUID, user_id: UUID, body: MemberRole, request: Request, actor=Depends(require_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        row = (await session.execute(text("SELECT * FROM app.change_member(:user,:role)"), {"user": user_id, "role": body.role})).mappings().one()
    return dict(row)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", operation_id="removeMember", status_code=204,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def remove_member(workspace_id: UUID, user_id: UUID, request: Request, actor=Depends(require_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        await session.execute(text("SELECT * FROM app.change_member(:user,NULL)"), {"user": user_id})
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/invitations", operation_id="listInvitations", response_model=InvitationPage)
async def list_invitations(workspace_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_owner)):
    return await owner_page(request, actor, "invitations", limit, cursor)


@router.post("/workspaces/{workspace_id}/invitations", operation_id="createInvitation", status_code=201,
    response_model=InvitationCreated, dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def create_invitation(workspace_id: UUID, body: InvitationInput, request: Request, actor=Depends(require_owner)):
    settings, _, _ = auth_service(request)
    token = secrets.token_urlsafe(32)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        row = (await session.execute(text("SELECT * FROM app.create_invitation(:email,:role,:hash)"),
            {"email": str(body.email), "role": body.role, "hash": digest(token)})).mappings().one()
    return {"invitation": dict(row), "acceptance_url": settings.origin + "/api/v1/invitations/" + token + "/accept"}


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}", operation_id="revokeInvitation", status_code=204,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def revoke_invitation(workspace_id: UUID, invitation_id: UUID, request: Request, actor=Depends(require_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        await session.execute(text("SELECT app.revoke_invitation(:id)"), {"id": invitation_id})
    return Response(status_code=204)


@router.post("/invitations/{token}/accept", operation_id="acceptInvitation", response_model=MemberView, openapi_extra=MUTATION)
async def accept_invitation(token: str, request: Request, user=Depends(require_csrf)):
    if len(token) != 43 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in token):
        raise HTTPException(404)
    async with membership_session(request, UUID(user["id"])) as session:
        row = (await session.execute(text("SELECT * FROM app.accept_invitation(:hash)"), {"hash": digest(token)})).mappings().one()
    return dict(row)
