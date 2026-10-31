"""Evaluation metadata reads inside the caller's tenant transaction."""

from sqlalchemy import text


async def evaluation_snapshot(session, project_id, collection_ids, generation_id):
    await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(generation_id)})
    generation = (await session.execute(text("SELECT * FROM app.index_generations WHERE id=:id"), {"id": generation_id})).mappings().first()
    if generation is None:
        raise ValueError("Unknown generation")
    size = await session.scalar(text("SELECT pg_relation_size('app.ix_chunks_embedding_hnsw')"))
    versions = (await session.execute(text("SELECT * FROM app.evaluation_versions(:project,:generation,CAST(:collections AS uuid[]))"),
        {"project": project_id, "collections": collection_ids, "generation": generation_id})).mappings().all()
    database = await session.scalar(text("SELECT version()"))
    extension = await session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    return generation, size, versions, database, extension
