"""Scope authorization and final RLS rechecks; no transaction ownership."""

from sqlalchemy import text
from docweave.rag.contracts import RetrievalError


SCOPE = "project_id=:project AND collection_id=ANY(CAST(:collections AS uuid[])) AND generation_id=:generation"

async def authorize(session, project_id, scopes, generation_id):
    await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(generation_id)})
    if await session.scalar(text("SELECT id FROM app.projects WHERE id=:id"), {"id": project_id}) is None:
        raise RetrievalError("not_found")
    if not scopes:
        return False
    found = (await session.execute(text("SELECT id FROM app.collections WHERE project_id=:project AND id=ANY(CAST(:ids AS uuid[]))"),
        {"project": project_id, "ids": scopes})).scalars().all()
    if set(found) != set(scopes):
        raise RetrievalError("not_found")
    if await session.scalar(text("SELECT id FROM app.index_generations WHERE id=:id AND enabled"), {"id": generation_id}) is None:
        raise RetrievalError("generation_unavailable")
    for collection in scopes:
        if not await session.scalar(text("SELECT app.index_policy(:collection,:generation,'read')"), {"collection": collection, "generation": generation_id}):
            raise RetrievalError("awaiting_approval")
    return True

async def inspect_snapshot(session, parameters):
    await session.execute(text("SET LOCAL statement_timeout='5s'"))
    await session.execute(text("SET LOCAL jit=off"))
    count, versions = (await session.execute(text(f"SELECT count(*),array_agg(DISTINCT document_version_id) FROM app.chunks WHERE {SCOPE}"), parameters)).one()
    return count, sorted(str(identity) for identity in (versions or []))

async def recheck(session, result):
    captured = {hit["chunk_id"] for channel in ("lexical", "vector") for hit in result[channel]}
    if captured:
        current = set((await session.execute(text("SELECT id FROM app.chunks WHERE id=ANY(CAST(:ids AS uuid[]))"), {"ids": list(captured)})).scalars())
        if current != captured:
            raise RetrievalError("scope_changed")
        if any(str(hit["document_version_id"]) not in result["snapshot_ids"] for channel in ("lexical", "vector") for hit in result[channel]):
            raise RetrievalError("scope_changed")
