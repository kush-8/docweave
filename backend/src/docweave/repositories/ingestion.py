"""Ingestion persistence; callers own transactions and connection lifetimes."""

from sqlalchemy import text


async def job_recoverable(connection, values):
    return await connection.scalar(text("SELECT app.ingestion_recoverable(:id)"), values)


async def acquire_worker_lock(connection):
    return await connection.scalar(text("SELECT pg_try_advisory_lock(730003)"))


async def claim_job(connection, values):
    return await connection.scalar(text("SELECT app.claim_ingestion(:id)"), values)


async def job_authorized(connection, values):
    return await connection.scalar(text("SELECT app.ingestion_authorized(:id,:token)"), values)


async def publish_version(connection, values):
    return await connection.scalar(text("SELECT app.publish_ingestion(:id,:token,:version,:hash,:config)"), values)


async def fail_job_permanently(connection, values):
    return await connection.execute(text("SELECT app.fail_ingestion(:id,:token,false)"), values)


async def fail_job_temporarily(connection, values):
    return await connection.execute(text("SELECT app.fail_ingestion(:id,:token,true)"), values)


async def release_worker_lock(connection):
    return await connection.execute(text("SELECT pg_advisory_unlock(730003)"))


async def retained_artifacts(connection):
    return await connection.execute(text("SELECT id FROM app.ingestion_artifacts()"))


async def resource_workspace(connection, values):
    return await connection.scalar(text("SELECT app.ingestion_resource(:kind,:id)"), values)


async def get_document(connection, values):
    return await connection.execute(text("SELECT * FROM app.documents WHERE id=:id"), values)


async def can_write_collection(connection, values):
    return await connection.scalar(text("SELECT app.collection_can(:id,'write')"), values)


async def enqueue_upload(connection, values):
    return await connection.scalar(text("SELECT app.enqueue_ingestion(:job,:collection,:document,:title,:media,:hash,:config,:request,NULL)"), values)


async def list_documents(connection, values):
    return await connection.execute(text("""SELECT * FROM app.documents WHERE collection_id=:collection
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""), values)


async def list_versions(connection, values):
    return await connection.execute(text("""SELECT *,captured_at AS created_at FROM app.document_versions_view(:document)
            WHERE CAST(:after AS timestamptz) IS NULL OR (captured_at,id)>(:after,:id) ORDER BY captured_at,id LIMIT :limit"""), values)


async def delete_document(connection, values):
    return await connection.scalar(text("SELECT app.delete_ingestion_document(:id)"), values)


async def get_job(connection, values):
    return await connection.execute(text("SELECT * FROM app.ingestion_jobs_view() WHERE id=:id"), values)


async def list_jobs(connection, values):
    return await connection.execute(text("""SELECT * FROM app.ingestion_jobs_view() WHERE project_id=:project
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""), values)


async def selection_for_import(connection, values):
    return await connection.scalar(text("SELECT app.selection_for_import(:selection,:collection)"), values)


async def enqueue_source(connection, values):
    return await connection.scalar(text("SELECT app.enqueue_ingestion(:job,:collection,NULL,:title,:media,:hash,:config,:request,:selection)"), values)


async def list_sources(connection, values):
    return await connection.execute(text("""SELECT * FROM app.sources_view() WHERE project_id=:project
            AND (CAST(:after AS timestamptz) IS NULL OR (created_at,id)>(:after,:id)) ORDER BY created_at,id LIMIT :limit"""), values)


async def get_source(connection, values):
    return await connection.execute(text("SELECT * FROM app.sources WHERE id=:id"), values)


async def delete_source(connection, values):
    return await connection.scalar(text("SELECT app.delete_ingestion_source(:id)"), values)
