import hashlib, inspect, json, subprocess, time
from uuid import UUID, uuid4
from urllib.parse import urlsplit
from docweave.rag.contracts import CONFIGURATION
from docweave.repositories import ingestion as repository
from docweave.db.sessions import domain_session
from docweave.core.errors import DomainError
from docweave.integrations.parser import container_parse


async def run_ingestion(job_id, *, engine, store, parser=container_parse, fetcher=None):
    """Claim under current authority, stage privately, then publish under a fresh check."""
    async with engine.connect() as connection:
        locked = await repository.acquire_worker_lock(connection)
        await connection.commit()
        if not locked:
            raise OSError("Ingestion worker busy")
        unpublished_artifact = None
        try:
            async with connection.begin():
                job = await repository.claim_job(connection, {"id": job_id})
            if not job:
                return
            token = UUID(job["token"])
            try:
                selection = job["selection"]
                async def authorize():
                    async with connection.begin():
                        allowed = await repository.job_authorized(connection, {"id": job_id, "token": token})
                    if not allowed:
                        raise ValueError("Ingestion authority changed")
                if selection:
                    from docweave.integrations.public_sources import fetch_document
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
                    result = await repository.publish_version(connection, {"id": job_id, "token": token, "version": version_id, "hash": parsed["sha256"], "config": parsed["configuration"]})
                if not result or result.get("version_id") != str(version_id):
                    unpublished_artifact = version_id
                if result and result.get("retry"):
                    raise OSError("Ingestion lease expired")
            except (ValueError, UnicodeError):
                async with connection.begin():
                    await repository.fail_job_permanently(connection, {"id": job_id, "token": token})
            except (OSError, TimeoutError, subprocess.TimeoutExpired):
                async with connection.begin():
                    await repository.fail_job_temporarily(connection, {"id": job_id, "token": token})
                raise OSError("Ingestion temporarily unavailable") from None
        finally:
            if unpublished_artifact:
                store.remove(unpublished_artifact)
            await repository.release_worker_lock(connection)
            await connection.commit()


async def reconcile_artifacts(engine, store, *, grace_seconds=300):
    async with engine.connect() as connection:
        retained = set(str(identity) for identity in (await repository.retained_artifacts(connection)).scalars())
    for path in store.root.iterdir():
        if path.is_file() and path.name not in retained and time.time() - path.stat().st_mtime >= grace_seconds:
            try:
                UUID(path.name)
            except ValueError:
                continue
            path.unlink(missing_ok=True)


async def document_row(engine, actor, document_id, *, write=False):
    async with domain_session(engine, actor.user_id, actor.workspace_id) as session:
        row = (await repository.get_document(session, {"id": document_id})).mappings().first()
        if row is None:
            raise DomainError("not_found")
        if write and not await repository.can_write_collection(session, {"id": row["collection_id"]}):
            raise DomainError("forbidden")
        return dict(row)


async def accept_upload(engine, store, actor, collection_id, upload, request_id, document_id=None):
    title, media, content = upload
    job = uuid4()
    store.put(job, content)
    try:
        async with domain_session(engine, actor.user_id, actor.workspace_id) as session:
            result = await repository.enqueue_upload(session, {"job": job, "collection": collection_id, "document": document_id, "title": title, "media": media,
                    "hash": hashlib.sha256(content).hexdigest(), "config": CONFIGURATION + ":" + media, "request": UUID(request_id)})
    except DomainError:
        store.remove(job)
        raise
    if UUID(result["job_id"]) != job:
        store.remove(job)
    return {**result, "status_url": f'/api/v1/jobs/{result["job_id"]}', "request_id": request_id}


async def accept_source(engine, actor, collection_id, selection_id, request_id, project_id=None):
    async with domain_session(engine, actor.user_id, actor.workspace_id) as session:
        selection = await repository.selection_for_import(session, {"selection": selection_id, "collection": collection_id})
        if selection is None:
            raise DomainError("not_found")
        if UUID(selection["project_id"]) != UUID(str(project_id or selection["project_id"])):
            raise DomainError("not_found")
        media = "text/markdown" if urlsplit(selection["source_url"]).path.endswith((".md", ".markdown")) else "text/plain"
        result = await repository.enqueue_source(session, {"job": uuid4(), "collection": collection_id, "title": selection["technology"] + " documentation",
                "hash": hashlib.sha256(selection["source_url"].encode()).hexdigest(), "config": CONFIGURATION + ":" + media, "media": media,
                "request": UUID(request_id), "selection": selection_id})
    return {"job_id": result["job_id"], "status_url": f'/api/v1/jobs/{result["job_id"]}', "request_id": request_id}
