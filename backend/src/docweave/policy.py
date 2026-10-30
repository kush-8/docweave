"""Workspace authority comes from the current database, never caller-supplied roles."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text

from docweave.auth import auth_service, require_user
from docweave.db import tenant_session
from docweave.models import Membership


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    workspace_id: UUID


async def membership_role(request, actor):
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        return await session.scalar(select(Membership.role).where(
            Membership.user_id == actor.user_id, Membership.workspace_id == actor.workspace_id))


async def require_actor(request: Request, user=Depends(require_user)) -> Actor:
    try:
        actor = Actor(UUID(user["id"]), UUID(request.path_params["workspace_id"]))
    except (ValueError, TypeError, KeyError):
        raise HTTPException(404) from None
    if await membership_role(request, actor) is None:
        raise HTTPException(404)
    return actor


async def require_owner(request: Request, actor=Depends(require_actor)) -> Actor:
    role = await membership_role(request, actor)
    if role is None:
        raise HTTPException(404)
    if role != "owner":
        raise HTTPException(403, detail="forbidden")
    return actor


async def require_project_actor(request: Request, user=Depends(require_user)) -> Actor:
    try:
        project_id = UUID(request.path_params["project_id"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(404) from None
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        workspace_id = await session.scalar(text("SELECT app.project_workspace(:project)"), {"project": project_id})
    if workspace_id is None:
        raise HTTPException(404)
    return Actor(UUID(user["id"]), workspace_id)


async def require_project_owner(request: Request, actor=Depends(require_project_actor)) -> Actor:
    return await require_owner(request, actor)
