import json
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from docweave.api.dependencies.auth import auth_service, require_csrf
from docweave.api.security import MUTATION
from docweave.core.pagination import decode_cursor, page
from docweave.api.dependencies.policy import require_project_actor, require_project_owner, require_collection_actor, require_collection_owner
from docweave.repositories import collections as repository
from docweave.schemas.collections import CollectionCreate, GrantSetInput, ProcessingPolicyInput, CollectionView, CollectionPage, GrantSet, ProcessingPolicy
from docweave.db.sessions import domain_session


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
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.list_collections(session, {"project": project_id, "after": after, "id": after_id, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/projects/{project_id}/collections", operation_id="createCollection", status_code=201, response_model=CollectionView,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def create_collection(project_id: UUID, body: CollectionCreate, request: Request, actor=Depends(require_project_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.create_collection(session, {"project": project_id, "name": body.name})


@router.get("/collections/{collection_id}/grants", operation_id="getCollectionGrants", response_model=GrantSet)
async def get_grants(collection_id: UUID, request: Request, actor=Depends(require_collection_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.get_grants(session, {"collection": collection_id})


@router.put("/collections/{collection_id}/grants", operation_id="replaceCollectionGrants", response_model=GrantSet,
    dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_grants(collection_id: UUID, body: GrantSetInput, request: Request, actor=Depends(require_collection_owner)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.replace_grants(session, {"collection": collection_id, "revision": body.expected_revision, "grants": json.dumps(body.model_dump(mode="json")["grants"])})


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


async def read_policy(request, actor, kind, resource_id):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.read_policy(session, {"kind": kind, "id": resource_id})


async def replace_policy(request, actor, kind, resource_id, body):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        return await repository.replace_policy(session, {"kind": kind, "id": resource_id, "revision": body.expected_revision, "processors": json.dumps(body.approved_processor_ids)})
