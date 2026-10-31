from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from docweave.api.dependencies.policy import require_actor, require_project_actor
from docweave.repositories import budget as repository
from docweave.schemas.budget import UsageReport
from docweave.db.sessions import domain_session
from docweave.api.dependencies.auth import auth_service


router = APIRouter(prefix="/api/v1", tags=["Usage"], responses={401: {"description": "Sign in required."},
    404: {"description": "Resource is missing or inaccessible."}, 422: {"description": "Invalid calendar month."}})


@router.get("/workspaces/{workspace_id}/usage", operation_id="getWorkspaceUsage", response_model=UsageReport, response_model_exclude_unset=True)
async def workspace_usage(workspace_id: UUID, request: Request, month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor=Depends(require_actor)):
    return await usage(request, actor, month)


@router.get("/projects/{project_id}/usage", operation_id="getProjectUsage", response_model=UsageReport, response_model_exclude_unset=True)
async def project_usage(project_id: UUID, request: Request, month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor=Depends(require_project_actor)):
    return await usage(request, actor, month, project_id)


async def usage(request, actor, month, project_id=None):
    try:
        period = date(int(month[:4]), int(month[5:]), 1) if month else None
    except ValueError:
        raise HTTPException(422) from None
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.usage(session, {"month": period, "project": project_id})
