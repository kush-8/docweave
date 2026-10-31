"""Operator-owned public fixture setup and current-policy checks on caller transactions."""

import json
from urllib.parse import urlsplit
from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert
from docweave.db.models import User, Workspace, Membership, Project, Collection, Processor, IndexGeneration, Document, DocumentVersion, DocumentationSelection, Source
from docweave.rag.contracts import HostedError
from docweave.repositories.compatibility import register_profile, complete_probe
from docweave.core.security import digest
from docweave.repositories.rag.scope import authorize as authorize_read


async def add(connection, table, **values):
    await connection.execute(insert(table).values(**values).on_conflict_do_nothing())


async def prepare(connection, context, records):
    if await connection.scalar(text("SELECT current_user")) != "docweave_migrator":
        raise HostedError("operator_login_required")
    await connection.execute(text("SELECT app.lock_budget()"))
    c = context
    if await connection.scalar(text("SELECT id FROM app.projects WHERE id=:id"), {"id": c["project"]}):
        return
    await add(connection, User, id=c["actor"].user_id, issuer="https://operator.docweave.invalid", subject="public-pilot-v1", display_name="Public fixture pilot")
    await add(connection, Workspace, id=c["actor"].workspace_id, name="Frozen public fixture pilot")
    await add(connection, Membership, workspace_id=c["actor"].workspace_id, user_id=c["actor"].user_id, role="owner")
    stack = [{"technology": "PostgreSQL", "docs_target": "17"}, {"technology": "FastAPI", "docs_target": "rolling:2026-10-31"}]
    await add(connection, Project, id=c["project"], workspace_id=c["actor"].workspace_id, name="Frozen public fixtures", goal="Evaluate only approved frozen public/synthetic documentation", stack=stack)
    await add(connection, Collection, id=c["collection"], workspace_id=c["actor"].workspace_id, project_id=c["project"], name="Approved frozen fixtures", is_default=True)
    await add(connection, Workspace, id=c["denied_workspace"], name="Synthetic inaccessible scope")
    await add(connection, Project, id=c["denied_project"], workspace_id=c["denied_workspace"], name="Denied fixture", goal="Synthetic isolation check")
    await add(connection, Collection, id=c["denied_collection"], workspace_id=c["denied_workspace"], project_id=c["denied_project"], name="Denied synthetic scope")
    for processor, provider, roles in ((c["embedding_processor"], "gemini", ["embedding"]), (c["ranking_processor"], "groq", ["reranking"])):
        await add(connection, Processor, id=processor, provider=provider, backend=provider + ":public-fixture-only", roles=roles, enabled=True)
        await connection.execute(text("UPDATE app.processors SET enabled=true WHERE id=:id"), {"id": processor})
        for table, column, identity in (("project_processor_approvals", "project_id", c["project"]), ("collection_processor_approvals", "collection_id", c["collection"])):
            await connection.execute(text(f"INSERT INTO app.{table}({column},workspace_id,processor_id,approved_by) VALUES(:id,:workspace,:processor,:actor) ON CONFLICT DO NOTHING"),
                {"id": identity, "workspace": c["actor"].workspace_id, "processor": processor, "actor": c["actor"].user_id})
    await add(connection, IndexGeneration, id=c["generation"], model="gemini-embedding-2", backend="google-generativelanguage:public-fixture-only", dimensions=768,
        normalization="unit-l2", chunker=records[0][1]["configuration"].rsplit(":", 1)[0], processor_ids=[c["embedding_processor"]], enabled=True)
    for meta, parsed in records:
        d = c["documents"][meta["file"]]
        source = None
        if meta["source_url"]:
            entry = stack[0] if meta["coverage"]["publisher_range"] == "17" else stack[1]
            url = urlsplit(meta["source_url"])
            await add(connection, DocumentationSelection, id=d["selection"], workspace_id=c["actor"].workspace_id, project_id=c["project"], approved_by=c["actor"].user_id,
                technology=entry["technology"], docs_target=entry["docs_target"], coverage=meta["coverage"], source_url=meta["source_url"],
                origin=f"{url.scheme}://{url.netloc}", path_prefix=url.path, attribution=meta["attribution"], approved_stack=entry)
            source = d["source"]
            await add(connection, Source, id=source, workspace_id=c["actor"].workspace_id, collection_id=c["collection"], source_selection_id=d["selection"])
        await add(connection, Document, id=d["id"], workspace_id=c["actor"].workspace_id, collection_id=c["collection"], source_id=source, title=meta["file"], media_type=meta["media_type"])
        await add(connection, DocumentVersion, id=d["version"], workspace_id=c["actor"].workspace_id, document_id=d["id"], content_hash=parsed["sha256"], configuration=parsed["configuration"], source_url=meta["source_url"])
        await connection.execute(update(Document).where(Document.id == d["id"]).values(active_version_id=d["version"]))
    await register_profile(connection, c["embedding_profile"], "gemini", "gemini-embedding-2", "google-generativelanguage", "embedding", "0.20", "0", 8192, 0)
    await register_profile(connection, c["ranking_profile"], "groq", "openai/gpt-oss-20b", "groq-cloud", "reranking", "0.075", "0.30", 131072, 4096)
    await connection.execute(text("SELECT app.set_workspace_allowance(:id,NULL,1)"), {"id": c["actor"].workspace_id})


async def authorize(session, context, *, document=None, chunk_ids=(), rerank=False):
    c = context
    await session.execute(text("SELECT app.lock_budget()"))
    await session.execute(text("SELECT id FROM app.workspaces WHERE id=:id FOR UPDATE"), {"id": c["actor"].workspace_id})
    await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(c["generation"])})
    if not await session.scalar(text("SELECT app.index_policy(:collection,:generation,'read')"), {"collection": c["collection"], "generation": c["generation"]}):
        raise HostedError("public_fixture_authority_changed")
    if document:
        snapshot = await session.scalar(text("SELECT app.index_input(:document,:generation)"), {"document": document["id"], "generation": c["generation"]})
        if snapshot["version_id"] != str(document["version"]) or snapshot["content_hash"] != document["hash"]:
            raise HostedError("public_fixture_version_changed")
    if rerank and not await session.scalar(text("""SELECT EXISTS (SELECT 1 FROM app.processors p JOIN app.project_processor_approvals a ON a.processor_id=p.id
        JOIN app.collection_processor_approvals b ON b.processor_id=p.id WHERE p.id=:processor AND p.enabled AND a.project_id=:project AND b.collection_id=:collection)"""),
        {"processor": c["ranking_processor"], "project": c["project"], "collection": c["collection"]}):
        raise HostedError("public_fixture_authority_changed")
    for identity in chunk_ids:
        if not await session.scalar(text("SELECT EXISTS(SELECT 1 FROM app.chunks WHERE id=:id AND project_id=:project AND collection_id=:collection AND app.chunk_current(document_version_id,collection_id,generation_id))"),
            {"id": identity, "project": c["project"], "collection": c["collection"]}):
            raise HostedError("public_fixture_authority_changed")


async def claim(session, context, body_hash, embedding):
    profile = context["embedding_profile" if embedding else "ranking_profile"]
    incoming, outgoing = (8192, 0) if embedding else (131072, 4096)
    key = digest("public-fixture:" + str(profile) + ":" + body_hash)
    await session.execute(text("""INSERT INTO app.compatibility_requests(operation_hash,request_hash,profile_id,input_tokens,output_tokens,purpose)
        VALUES(:key,:hash,:profile,:incoming,:outgoing,'public_fixture') ON CONFLICT DO NOTHING"""),
        {"key": key, "hash": body_hash, "profile": profile, "incoming": incoming, "outgoing": outgoing})
    row = (await session.execute(text("SELECT request_hash,profile_id,input_tokens,output_tokens,purpose FROM app.compatibility_requests WHERE operation_hash=:key"), {"key": key})).one()
    if tuple(row) != (body_hash, profile, incoming, outgoing, "public_fixture"):
        raise HostedError("public_fixture_registration_changed")
    return await session.scalar(text("SELECT app.claim_compatibility_probe(:key,:hash,:project)"), {"key": key, "hash": body_hash, "project": context["project"]})


async def compatible_chunks(session, context, target):
    await authorize_read(session, context["project"], [context["collection"]], context["generation"])
    return await session.scalar(text("""SELECT count(*) FROM app.chunks WHERE project_id=:project AND collection_id=:collection
        AND generation_id=:generation AND provenance->>'docs_target'=:target"""),
        {"project": context["project"], "collection": context["collection"], "generation": context["generation"], "target": target})
