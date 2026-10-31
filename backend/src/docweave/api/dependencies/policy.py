from uuid import UUID
from fastapi import Depends, HTTPException, Request
from docweave.api.dependencies.auth import auth_service, require_user
from docweave.db.sessions import tenant_session
from docweave.core.identity import Actor
from docweave.repositories import policy as repository, ingestion as ingestion_repository


async def membership_role(request, actor):
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        return await repository.membership_role(session, actor)


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
        workspace_id = await repository.project_workspace(session, {"project": project_id})
    if workspace_id is None:
        raise HTTPException(404)
    return Actor(UUID(user["id"]), workspace_id)


async def require_project_owner(request: Request, actor=Depends(require_project_actor)) -> Actor:
    return await require_owner(request, actor)


async def require_collection_actor(request: Request, user=Depends(require_user)) -> Actor:
    try:
        collection_id = UUID(request.path_params["collection_id"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(404) from None
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        workspace_id = await repository.collection_workspace(session, {"collection": collection_id})
    if workspace_id is None:
        raise HTTPException(404)
    return Actor(UUID(user["id"]), workspace_id)


async def require_collection_owner(request: Request, actor=Depends(require_collection_actor)) -> Actor:
    return await require_owner(request, actor)


async def require_collection_writer(request: Request, actor=Depends(require_collection_actor)) -> Actor:
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        writable = await repository.collection_writable(session, {"collection": UUID(request.path_params["collection_id"])})
    if not writable:
        raise HTTPException(403, detail="forbidden")
    return actor

async def require_resource_actor(request: Request, user=Depends(require_user)):
    kind, identity = next(((kind, request.path_params.get(kind + "_id")) for kind in ("document", "job", "source") if kind + "_id" in request.path_params))
    try:
        identity = UUID(identity)
    except ValueError:
        raise HTTPException(404) from None
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        workspace = await ingestion_repository.resource_workspace(session, {"kind": kind, "id": identity})
    if workspace is None:
        raise HTTPException(404)
    return Actor(UUID(user["id"]), workspace)
