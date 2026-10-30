"""Durable bounded text snapshots. No hosted inference or retrieval index is enabled."""

import asyncio
import hashlib
import inspect
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.datastructures import UploadFile

from docweave.auth import auth_service, require_csrf, require_user
from docweave.db import tenant_session
from docweave.memberships import MUTATION, membership_session
from docweave.pagination import decode_cursor, page
from docweave.policy import Actor, require_collection_actor, require_collection_writer, require_project_actor
from docweave.projects import StrictInput
from docweave.text_parser import CONFIGURATION, MAX_BYTES

ROOT = Path(__file__).resolve().parents[3]


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, identity):
        return self.root / str(UUID(str(identity)))

    def put(self, identity, content):
        with self.path(identity).open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

    def read(self, identity):
        with self.path(identity).open("rb") as file:
            content = file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("Oversized artifact")
        return content

    def remove(self, identity):
        self.path(identity).unlink(missing_ok=True)


def storage_root():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    return Path(values.get("INGESTION_STORAGE_ROOT") or ROOT / "storage").resolve()


def storage(request):
    if not hasattr(request.app.state, "ingestion_store"):
        request.app.state.ingestion_store = ArtifactStore(storage_root())
    return request.app.state.ingestion_store


async def container_parse(content, media_type):
    name = "docweave-parser-" + uuid4().hex
    command = ["docker", "run", "--rm", "--name", name, "-i", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=512m", "--memory-swap=512m", "--cpus=1",
        "--pids-limit=16", "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "docweave-text-parser:3a", media_type]
    def parse():
        try:
            process = subprocess.run(command, input=content, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
            if process.returncode == 2:
                raise ValueError("Invalid text")
            if process.returncode:
                raise OSError("Parser unavailable")
            return json.loads(process.stdout)
        finally:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    return await asyncio.to_thread(parse)


async def run_ingestion(job_id, *, engine, store, parser=container_parse, fetcher=None):
    """Claim under current authority, stage privately, then publish under a fresh check."""
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(730003)"))
        await connection.commit()
        if not locked:
            raise OSError("Ingestion worker busy")
        unpublished_artifact = None
        try:
            async with connection.begin():
                job = await connection.scalar(text("SELECT app.claim_ingestion(:id)"), {"id": job_id})
            if not job:
                return
            token = UUID(job["token"])
            try:
                selection = job["selection"]
                async def authorize():
                    async with connection.begin():
                        allowed = await connection.scalar(text("SELECT app.ingestion_authorized(:id,:token)"), {"id": job_id, "token": token})
                    if not allowed:
                        raise ValueError("Ingestion authority changed")
                if selection:
                    from docweave.sources import fetch_document
                    content, _ = await fetcher(selection) if fetcher else await fetch_document(selection, authorize=authorize)
                else:
                    content = store.read(job_id)
                await authorize()
                parsed = parser(content, job["media_type"])
                if inspect.isawaitable(parsed):
                    parsed = await parsed
                version_id = uuid4()
                unpublished_artifact = version_id
                store.put(version_id, json.dumps(parsed, ensure_ascii=False).encode())
                # A lost commit acknowledgement must not erase a referenced snapshot.
                unpublished_artifact = None
                async with connection.begin():
                    result = await connection.scalar(text("SELECT app.publish_ingestion(:id,:token,:version,:hash,:config)"),
                        {"id": job_id, "token": token, "version": version_id, "hash": parsed["sha256"], "config": parsed["configuration"]})
                if not result or result.get("version_id") != str(version_id):
                    unpublished_artifact = version_id
                if result and result.get("retry"):
                    raise OSError("Ingestion lease expired")
            except (ValueError, UnicodeError):
                async with connection.begin():
                    await connection.execute(text("SELECT app.fail_ingestion(:id,:token,false)"), {"id": job_id, "token": token})
            except (OSError, TimeoutError, subprocess.TimeoutExpired):
                async with connection.begin():
                    await connection.execute(text("SELECT app.fail_ingestion(:id,:token,true)"), {"id": job_id, "token": token})
                raise OSError("Ingestion temporarily unavailable") from None
        finally:
            if unpublished_artifact:
                store.remove(unpublished_artifact)
            await connection.execute(text("SELECT pg_advisory_unlock(730003)"))
            await connection.commit()


async def reconcile_artifacts(engine, store, *, grace_seconds=300):
    async with engine.connect() as connection:
        retained = set(str(identity) for identity in (await connection.execute(text("SELECT id FROM app.ingestion_artifacts()"))).scalars())
    for path in store.root.iterdir():
        if path.is_file() and path.name not in retained and time.time() - path.stat().st_mtime >= grace_seconds:
            try:
                UUID(path.name)
            except ValueError:
                continue
            path.unlink(missing_ok=True)


async def require_resource_actor(request: Request, user=Depends(require_user)):
    kind, identity = next(((kind, request.path_params.get(kind + "_id")) for kind in ("document", "job", "source") if kind + "_id" in request.path_params))
    try:
        identity = UUID(identity)
    except ValueError:
        raise HTTPException(404) from None
    _, engine, _ = auth_service(request)
    async with tenant_session(engine, actor_id=UUID(user["id"])) as session:
        workspace = await session.scalar(text("SELECT app.ingestion_resource(:kind,:id)"), {"kind": kind, "id": identity})
    if workspace is None:
        raise HTTPException(404)
    return Actor(UUID(user["id"]), workspace)


async def document_row(request, actor, document_id, *, write=False):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        row = (await session.execute(text("SELECT * FROM app.documents WHERE id=:id"), {"id": document_id})).mappings().first()
        if row is None:
            raise HTTPException(404)
        if write and not await session.scalar(text("SELECT app.collection_can(:id,'write')"), {"id": row["collection_id"]}):
            raise HTTPException(403, detail="forbidden")
        return dict(row)


class DocumentView(BaseModel):
    id: UUID
    collection_id: UUID
    title: str
    media_type: str
    status: str
    malware_scan: str = "disabled"
    active_version_id: UUID | None = None


class DocumentPage(BaseModel):
    items: list[DocumentView]
    next_cursor: str | None


class ImportInput(StrictInput):
    source_selection_id: UUID
    collection_id: UUID


router = APIRouter(prefix="/api/v1", tags=["Knowledge"], responses={401: {"description": "Sign in required."},
    403: {"description": "Insufficient authority or invalid Origin/CSRF."}, 404: {"description": "Missing or inaccessible."},
    409: {"description": "Another ingestion is active."}, 422: {"description": "Invalid bounded TXT/Markdown input."}})


async def bounded_upload(request):
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(422)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BYTES + 65536:
            raise HTTPException(413)
        body.extend(chunk)
    async def stream():
        yield bytes(body)
    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=0).parse()
    except (MultiPartException, ValueError):
        raise HTTPException(422) from None
    try:
        values = form.getlist("file")
        if len(form) != 1 or len(values) != 1 or not isinstance(values[0], UploadFile):
            raise HTTPException(422)
        file = values[0]
        name = file.filename or ""
        if not 1 <= len(name) <= 200 or any(c in name for c in ("/", "\\", "\x00")) or name.startswith("."):
            raise HTTPException(422)
        media = file.content_type
        if (Path(name).suffix.lower(), media) not in ((".txt", "text/plain"), (".md", "text/markdown"), (".markdown", "text/markdown")):
            raise HTTPException(422)
        content = await file.read(MAX_BYTES + 1)
        if not content or len(content) > MAX_BYTES:
            raise HTTPException(422)
        return name, media, content
    finally:
        await form.close()


async def accept_upload(request, actor, collection_id, document_id=None):
    title, media, content = await bounded_upload(request)
    store = storage(request)
    job = uuid4()
    store.put(job, content)
    try:
        async with membership_session(request, actor.user_id, actor.workspace_id) as session:
            result = await session.scalar(text("SELECT app.enqueue_ingestion(:job,:collection,:document,:title,:media,:hash,:config,:request,NULL)"),
                {"job": job, "collection": collection_id, "document": document_id, "title": title, "media": media,
                    "hash": hashlib.sha256(content).hexdigest(), "config": CONFIGURATION + ":" + media, "request": UUID(request.state.request_id)})
    except HTTPException:
        store.remove(job)
        raise
    if UUID(result["job_id"]) != job:
        store.remove(job)
    return {**result, "status_url": f'/api/v1/jobs/{result["job_id"]}', "request_id": request.state.request_id}


@router.post("/collections/{collection_id}/documents", status_code=202, operation_id="uploadDocument",
    dependencies=[Depends(require_csrf)], openapi_extra={**MUTATION, "requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "required": ["file"], "additionalProperties": False, "properties": {"file": {"type": "string", "format": "binary"}}}}}}})
async def upload_document(collection_id: UUID, request: Request, actor=Depends(require_collection_writer)):
    return await accept_upload(request, actor, collection_id)


@router.get("/collections/{collection_id}/documents", operation_id="listDocuments", response_model=DocumentPage)
async def list_documents(collection_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_collection_actor)):
    settings, _, _ = auth_service(request)
    resource = f"documents:{collection_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(text("""SELECT * FROM app.documents WHERE collection_id=:collection
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""),
            {"collection": collection_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [{**DocumentView(**row).model_dump(mode="json"), "created_at": row["created_at"]} for row in rows], limit, actor.user_id, resource)


@router.get("/documents/{document_id}", operation_id="getDocument", response_model=DocumentView)
async def get_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    return await document_row(request, actor, document_id)


@router.get("/documents/{document_id}/versions", operation_id="listDocumentVersions")
async def list_versions(document_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_resource_actor)):
    settings, _, _ = auth_service(request)
    resource = f"versions:{document_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(text("""SELECT *,captured_at AS created_at FROM app.document_versions_view(:document)
            WHERE CAST(:after AS timestamptz) IS NULL OR (captured_at,id)>(:after,:id) ORDER BY captured_at,id LIMIT :limit"""),
            {"document": document_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/documents/{document_id}/versions", status_code=202, operation_id="replaceDocument", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def replace_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    row = await document_row(request, actor, document_id, write=True)
    return await accept_upload(request, actor, row["collection_id"], document_id)


@router.delete("/documents/{document_id}", status_code=202, operation_id="deleteDocument", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def delete_document(document_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        result = await session.scalar(text("SELECT app.delete_ingestion_document(:id)"), {"id": document_id})
    for identity in result.pop("artifacts"):
        storage(request).remove(identity)
    return result


@router.get("/jobs/{job_id}", operation_id="getJob", tags=["Jobs"])
async def get_job(job_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        result = (await session.execute(text("SELECT * FROM app.ingestion_jobs_view() WHERE id=:id"), {"id": job_id})).mappings().first()
    if result is None:
        raise HTTPException(404)
    return {key: value for key, value in result.items() if key not in ("document_id", "collection_id", "project_id")}


@router.get("/projects/{project_id}/jobs", operation_id="listProjectJobs", tags=["Jobs"])
async def list_jobs(project_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_project_actor)):
    settings, _, _ = auth_service(request)
    resource = f"jobs:{project_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(text("""SELECT * FROM app.ingestion_jobs_view() WHERE project_id=:project
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""),
            {"project": project_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [{k: v for k, v in row.items() if k not in ("document_id", "collection_id", "project_id")} for row in rows], limit, actor.user_id, resource)


async def accept_source(request, actor, collection_id, selection_id):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        selection = await session.scalar(text("SELECT app.selection_for_import(:selection,:collection)"), {"selection": selection_id, "collection": collection_id})
        if selection is None:
            raise HTTPException(404)
        if UUID(selection["project_id"]) != UUID(request.path_params.get("project_id", selection["project_id"])):
            raise HTTPException(404)
        media = "text/markdown" if urlsplit(selection["source_url"]).path.endswith((".md", ".markdown")) else "text/plain"
        result = await session.scalar(text("SELECT app.enqueue_ingestion(:job,:collection,NULL,:title,:media,:hash,:config,:request,:selection)"),
            {"job": uuid4(), "collection": collection_id, "title": selection["technology"] + " documentation",
                "hash": hashlib.sha256(selection["source_url"].encode()).hexdigest(), "config": CONFIGURATION + ":" + media, "media": media,
                "request": UUID(request.state.request_id), "selection": selection_id})
    return {"job_id": result["job_id"], "status_url": f'/api/v1/jobs/{result["job_id"]}', "request_id": request.state.request_id}


@router.post("/projects/{project_id}/sources", status_code=202, operation_id="importSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def import_source(project_id: UUID, body: ImportInput, request: Request, actor=Depends(require_project_actor)):
    return await accept_source(request, actor, body.collection_id, body.source_selection_id)


@router.get("/projects/{project_id}/sources", operation_id="listSources")
async def list_sources(project_id: UUID, request: Request, limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=2048), actor=Depends(require_project_actor)):
    settings, _, _ = auth_service(request)
    resource = f"sources:{project_id}:v1"
    after, identity = decode_cursor(settings, cursor, actor.user_id, resource)
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        rows = (await session.execute(text("""SELECT * FROM app.sources_view() WHERE project_id=:project
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""),
            {"project": project_id, "after": after, "id": identity, "limit": limit + 1})).mappings().all()
    return page(settings, [dict(row) for row in rows], limit, actor.user_id, resource)


@router.post("/sources/{source_id}/refresh", status_code=202, operation_id="refreshSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def refresh_source(source_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        source = (await session.execute(text("SELECT * FROM app.sources WHERE id=:id"), {"id": source_id})).mappings().first()
    if source is None:
        raise HTTPException(404)
    return await accept_source(request, actor, source["collection_id"], source["source_selection_id"])


@router.delete("/sources/{source_id}", status_code=202, operation_id="deleteSource", dependencies=[Depends(require_csrf)], openapi_extra=MUTATION)
async def delete_source(source_id: UUID, request: Request, actor=Depends(require_resource_actor)):
    async with membership_session(request, actor.user_id, actor.workspace_id) as session:
        result = await session.scalar(text("SELECT app.delete_ingestion_source(:id)"), {"id": source_id})
    for identity in result.pop("artifacts"):
        storage(request).remove(identity)
    return result
