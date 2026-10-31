import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from docweave.api.dependencies.auth import auth_service, require_csrf
from docweave.core.security import digest
from docweave.core.pagination import decode_cursor, page
from docweave.api.dependencies.policy import require_owner
from docweave.repositories import memberships as repository
from docweave.schemas.memberships import MemberRole, InvitationInput, MemberView, InvitationCreated, MemberPage, InvitationPage
from docweave.db.sessions import domain_session
from docweave.api.security import MUTATION


router = APIRouter(prefix="/api/v1", tags=["Workspaces"], responses={
    400: {"description": "Invalid cursor."}, 401: {"description": "Sign in required."},
    403: {"description": "Invalid origin/CSRF or insufficient workspace role."},
    404: {"description": "Resource is missing or inaccessible."},
    409: {"description": "Last-owner protection or already a workspace member."},
    422: {"description": "Invalid input."},
})


@router.get("/workspaces/{workspace_id}/members", operation_id="listMembers", response_model=MemberPage)
async def list_members(workspace_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_owner)):
    return await owner_page(request, actor, "members", limit, cursor)


@router.patch("/workspaces/{workspace_id}/members/{user_id}", operation_id="updateMemberRole", response_model=MemberView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def update_member(workspace_id: UUID, user_id: UUID, body: MemberRole, request: Request, actor=Depends(require_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        row = (await repository.update_member(session, {"user": user_id, "role": body.role})).mappings().one()
    return dict(row)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", operation_id="removeMember", status_code=204,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def remove_member(workspace_id: UUID, user_id: UUID, request: Request, actor=Depends(require_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        await repository.remove_member(session, {"user": user_id})
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
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        row = (await repository.create_invitation(session, {"email": str(body.email), "role": body.role, "hash": digest(token)})).mappings().one()
    return {"invitation": dict(row), "acceptance_url": settings.origin + "/api/v1/invitations/" + token + "/accept"}


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}", operation_id="revokeInvitation", status_code=204,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def revoke_invitation(workspace_id: UUID, invitation_id: UUID, request: Request, actor=Depends(require_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        await repository.revoke_invitation(session, {"id": invitation_id})
    return Response(status_code=204)


@router.post("/invitations/{token}/accept", operation_id="acceptInvitation", response_model=MemberView, openapi_extra=MUTATION)
async def accept_invitation(token: str, request: Request, user=Depends(require_csrf)):
    if len(token) != 43 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in token):
        raise HTTPException(404)
    async with domain_session(auth_service(request)[1], UUID(user["id"])) as session:
        row = (await repository.accept_invitation(session, {"hash": digest(token)})).mappings().one()
    return dict(row)


async def owner_page(request, actor, kind, limit, cursor):
    settings, _, _ = auth_service(request)
    resource = f"{kind}:{actor.workspace_id}:v1"
    after, after_id = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.owner_page(session, kind, {"after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)
