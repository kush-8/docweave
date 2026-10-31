from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from docweave.api.dependencies.auth import auth_service, require_csrf
from docweave.api.security import MUTATION
from docweave.core.pagination import decode_cursor, page
from docweave.api.dependencies.policy import require_collection_actor, require_collection_writer, require_project_actor, require_resource_actor
from docweave.repositories import ingestion as repository
from docweave.schemas.ingestion import DocumentView, DocumentPage, ImportInput
from docweave.db.sessions import domain_session
from docweave.api.dependencies.storage import storage
from docweave.api.uploads import bounded_upload
from docweave.services.ingestion import accept_upload, accept_source, document_row


router = APIRouter(prefix="/api/v1", tags=["Knowledge"], responses={401: {"description": "Sign in required."},
    403: {"description": "Insufficient authority or invalid Origin/CSRF."}, 404: {"description": "Missing or inaccessible."},
    409: {"description": "Another ingestion is active."}, 422: {"description": "Invalid bounded TXT/Markdown input."}})


@router.post("/collections/{collection_id}/documents", status_code=202, operation_id="uploadDocument",
    dependencies=[Depends(require_csrf)], openapi_extra={**MUTATION, "requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "required": ["file"], "additionalProperties": False, "properties": {"file": {"type": "string", "format": "binary"}}}}}}})
async def upload_document(collection_id: UUID, request: Request, actor=Depends(require_collection_writer)):
    return await accept_upload(auth_service(request)[1], storage(request), actor, collection_id, await bounded_upload(request), request.state.request_id)


@router.get("/collections/{collection_id}/documents", operation_id="listDocuments", response_model=DocumentPage)
async def list_documents(collection_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_collection_actor)):
    settings, _, _ = auth_service(request)
    resource = f"documents:{collection_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.list_documents(session, {"collection": collection_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [{**DocumentView(**row).model_dump(mode="json"), "created_at": row["created_at"]} for row in rows], limit, actor.user_id, resource)


@router.get("/documents/{document_id}", operation_id="getDocument", response_model=DocumentView)
async def get_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    return await document_row(auth_service(request)[1], actor, document_id)


@router.get("/documents/{document_id}/versions", operation_id="listDocumentVersions")
async def list_versions(document_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_resource_actor)):
    settings, _, _ = auth_service(request)
    resource = f"versions:{document_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.list_versions(session, {"document": document_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/documents/{document_id}/versions", status_code=202, operation_id="replaceDocument", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    row = await document_row(auth_service(request)[1], actor, document_id, write=True)
    return await accept_upload(auth_service(request)[1], storage(request), actor, row["collection_id"], await bounded_upload(request), request.state.request_id, document_id)


@router.delete("/documents/{document_id}", status_code=202, operation_id="deleteDocument", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def delete_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        result = await repository.delete_document(session, {"id": document_id})
    for identity in result.pop("artifacts"):
        storage(request).remove(identity)
    return result


@router.get("/jobs/{job_id}", operation_id="getJob", tags=["Jobs"])
async def get_job(job_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        result = (await repository.get_job(session, {"id": job_id})).mappings().first()
    if result is None:
        raise HTTPException(404)
    return {key: value for key, value in result.items() if key not in ("document_id", "collection_id", "project_id")}


@router.get("/projects/{project_id}/jobs", operation_id="listProjectJobs", tags=["Jobs"])
async def list_jobs(project_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_project_actor)):
    settings, _, _ = auth_service(request)
    resource = f"jobs:{project_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.list_jobs(session, {"project": project_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [{k: v for k, v in row.items() if k not in ("document_id", "collection_id", "project_id")} for row in rows], limit, actor.user_id, resource)


@router.post("/projects/{project_id}/sources", status_code=202, operation_id="importSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def import_source(project_id: UUID, body: ImportInput, request: Request, actor=Depends(require_project_actor)):
    return await accept_source(auth_service(request)[1], actor, body.collection_id, body.source_selection_id, request.state.request_id, project_id)


@router.get("/projects/{project_id}/sources", operation_id="listSources")
async def list_sources(project_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_project_actor)):
    settings, _, _ = auth_service(request)
    resource = f"sources:{project_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        rows = (await repository.list_sources(session, {"project": project_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/sources/{source_id}/refresh", status_code=202, operation_id="refreshSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def refresh_source(source_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        source = (await repository.get_source(session, {"id": source_id})).mappings().first()
    if source is None:
        raise HTTPException(404)
    return await accept_source(auth_service(request)[1], actor, source["collection_id"], source["source_selection_id"], request.state.request_id)


@router.delete("/sources/{source_id}", status_code=202, operation_id="deleteSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def delete_source(source_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with domain_session(auth_service(request)[1], actor.user_id, actor.workspace_id) as session:
        result = await repository.delete_source(session, {"id": source_id})
    for identity in result.pop("artifacts"):
        storage(request).remove(identity)
    return result
