"""Current collection access and separate, explicit processor consent."""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from docweave.auth import auth_service, require_csrf
from docweave.memberships import MUTATION, membership_session
from docweave.pagination import decode_cursor, page
from docweave.policy import require_project_actor, require_project_owner, require_collection_actor, require_collection_owner
from docweave.projects import Nonblank, StrictInput

Revision = Annotated[int, Field(ge=1, le=2147483647, strict=True)]


class CollectionCreate(StrictInput):
    name: Nonblank


class Grant(StrictInput):
    user_id: UUID
    access: Literal["read", "write"]


class GrantSetInput(StrictInput):
    expected_revision: Revision
    grants: list[Grant]

    @model_validator(mode="after")
    def unique_members(self):
        if len({grant.user_id for grant in self.grants}) != len(self.grants):
            raise ValueError("One grant per member is allowed.")
        return self


class ProcessingPolicyInput(StrictInput):
    expected_revision: Revision
    approved_processor_ids: list[Nonblank] = Field(json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def unique_processors(self):
        if len(set(self.approved_processor_ids)) != len(self.approved_processor_ids):
            raise ValueError("Processor IDs must be unique.")
        return self


class CollectionView(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    can_write: bool


class CollectionPage(BaseModel):
    items: list[CollectionView]
    next_cursor: str | None


class GrantSet(BaseModel):
    revision: int
    grants: list[Grant]


class ProcessingPolicy(BaseModel):
    revision: int
    approved_processor_ids: list[str]


router = APIRouter(prefix="/api/v1", tags=["Knowledge"], responses={
    400: {"description": "Invalid cursor."}, 401: {"description": "Sign in required."},
    403: {"description": "Invalid Origin/CSRF or insufficient authority."},
    404: {"description": "Resource is missing or inaccessible."},
    409: {"description": "Revision changed; reload before editing."}, 422: {"description": "Invalid input."},
})


@router.get("/projects/{project_id}/collections", operation_id="listCollections", response_model=CollectionPage)
async def list_collections(project_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_project_actor)):
    settings, _, _ = auth_service(request)
    resource = f"collections:{project_id}:v1"
    after, after_id = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(text("""
            SELECT c.id,c.created_at,c.project_id,c.name,app.collection_can(c.id,'write') AS can_write FROM app.collections c
            WHERE c.project_id=:project AND (CAST(:after AS timestamptz) IS NULL OR (c.created_at,c.id)>(:after,:id))
            ORDER BY c.created_at,c.id LIMIT :limit
        """), {"project": project_id, "after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/projects/{project_id}/collections", operation_id="createCollection", status_code=201, response_model=CollectionView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def create_collection(project_id: UUID, body: CollectionCreate, request: Request, actor=Depends(require_project_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.create_collection(:project,:name)"), {"project": project_id, "name": body.name})


@router.get("/collections/{collection_id}/grants", operation_id="getCollectionGrants", response_model=GrantSet)
async def get_grants(collection_id: UUID, request: Request, actor=Depends(require_collection_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.collection_grants(:collection)"), {"collection": collection_id})


@router.put("/collections/{collection_id}/grants", operation_id="replaceCollectionGrants", response_model=GrantSet,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_grants(collection_id: UUID, body: GrantSetInput, request: Request, actor=Depends(require_collection_owner)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.replace_collection_grants(:collection,:revision,CAST(:grants AS jsonb))"),
            {"collection": collection_id, "revision": body.expected_revision, "grants": json.dumps(body.model_dump(mode="json")["grants"])})


async def read_policy(request, actor, kind, resource_id):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.processing_policy(:kind,:id)"), {"kind": kind, "id": resource_id})


async def replace_policy(request, actor, kind, resource_id, body):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        return await session.scalar(text("SELECT app.replace_processing_policy(:kind,:id,:revision,CAST(:processors AS jsonb))"),
            {"kind": kind, "id": resource_id, "revision": body.expected_revision, "processors": json.dumps(body.approved_processor_ids)})


@router.get("/projects/{project_id}/processing-policy", operation_id="getProjectProcessingPolicy", response_model=ProcessingPolicy)
async def get_project_policy(project_id: UUID, request: Request, actor=Depends(require_project_actor)):
    return await read_policy(request, actor, "project", project_id)


@router.put("/projects/{project_id}/processing-policy", operation_id="replaceProjectProcessingPolicy", response_model=ProcessingPolicy,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_project_policy(project_id: UUID, body: ProcessingPolicyInput, request: Request, actor=Depends(require_project_owner)):
    return await replace_policy(request, actor, "project", project_id, body)


@router.get("/collections/{collection_id}/processing-policy", operation_id="getCollectionProcessingPolicy", response_model=ProcessingPolicy)
async def get_collection_policy(collection_id: UUID, request: Request, actor=Depends(require_collection_actor)):
    return await read_policy(request, actor, "collection", collection_id)


@router.put("/collections/{collection_id}/processing-policy", operation_id="replaceCollectionProcessingPolicy", response_model=ProcessingPolicy,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_collection_policy(collection_id: UUID, body: ProcessingPolicyInput, request: Request, actor=Depends(require_collection_owner)):
    return await replace_policy(request, actor, "collection", collection_id, body)
