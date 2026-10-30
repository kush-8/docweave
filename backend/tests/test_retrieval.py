"""All retrieval strategies share current database scope; fake vectors prove behavior only."""

import json
import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_auth import auth_client  # noqa: F401
from test_collections import collections, configure_processors, policy_path, replace_grants  # noqa: F401
from test_database import B, WB, databases, test_urls  # noqa: F401
from test_ingestion import ingestion, metadata, upload, work  # noqa: F401
from test_memberships import members  # noqa: F401

pytestmark = pytest.mark.anyio


def basis(position=0):
    return [float(index == position) for index in range(768)]


@pytest.fixture
async def indexed(ingestion):
    from docweave.policy import Actor
    from docweave.retrieval import index_document
    c = ingestion
    await configure_processors(c)
    for kind in ("project", "collection"):
        result = await c["admin"].put(policy_path(c, kind), json={"expected_revision": 1,
            "approved_processor_ids": ["test:gemini:embedding:v1"]}, headers=c["headers"])
        assert result.status_code == 200
    c["generation"] = uuid4()
    async with c["owner"].begin() as connection:
        await connection.execute(text("""INSERT INTO app.index_generations(id,model,backend,dimensions,normalization,chunker,processor_ids,enabled)
            VALUES(:id,'test-recorded-768','fixture',768,'unit-l2',:chunker,CAST(:processors AS jsonb),true)"""),
            {"id": c["generation"], "chunker": "utf8-lf:headings:whitespace350-overlap50:v1",
                "processors": json.dumps(["test:gemini:embedding:v1"])})
    c["actor"] = Actor(UUID(c["user"]["id"]), UUID(c["workspace"]["id"]))
    c["reader"] = Actor(UUID(c["recipient"]["id"]), UUID(c["workspace"]["id"]))
    return c


async def fake_vectors(bodies):
    return [basis(1 if "beta" in body.lower() else 0) for body in bodies]


async def index(c, content):
    from docweave.retrieval import index_document
    accepted = (await upload(c, content)).json()
    await work(c, accepted["job_id"])
    await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"],
        worker_engine=c["worker"], store=c["store"], embedder=fake_vectors)
    return accepted


async def retrieve(c, query, *, lexical="native", vector="exact", actor=None, scopes=None, generation=None, explain=False):
    from docweave.retrieval import retrieve_channels
    return await retrieve_channels(actor or c["actor"], UUID(c["project"]), query,
        collection_ids=[UUID(c["collection"])] if scopes is None else scopes, generation_id=generation or c["generation"],
        query_vector=basis(), lexical=lexical, vector=vector, engine=c["runtime"], explain=explain)


@pytest.mark.parametrize("lexical", ["native", "bm25"])
async def test_lexical_paths_preserve_literal_error_codes_and_exact_spans(indexed, lexical):
    c = indexed
    accepted = await index(c, b"# Access\n\nERR_CONNECTION_001 refers to pg_hba.conf and SQLSTATE 28000.\n")
    result = await retrieve(c, "ERR_CONNECTION_001", lexical=lexical)
    assert len(result["lexical"]) == 1
    hit = result["lexical"][0]
    assert str(hit["document_id"]) == accepted["document_id"]
    assert "ERR_CONNECTION_001" in hit["quote"] and hit["locator"]["heading"] == "Access"
    assert str(hit["generation_id"]) == str(c["generation"])


async def test_empty_and_revoked_scopes_never_broaden(indexed):
    from docweave.retrieval import RetrievalError
    c = indexed
    await index(c, b"Secret alpha connection.\n")
    empty = await retrieve(c, "alpha", scopes=[])
    assert empty["lexical"] == [] and empty["vector"] == []
    with pytest.raises(RetrievalError, match="not_found"):
        await retrieve(c, "alpha", actor=c["reader"])
    await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    assert (await retrieve(c, "alpha", actor=c["reader"]))["lexical"]
    await replace_grants(c, [], revision=2)
    with pytest.raises(RetrievalError, match="not_found"):
        await retrieve(c, "alpha", actor=c["reader"])


async def test_unapproved_private_text_never_reaches_fake_embedding(indexed):
    from docweave.retrieval import RetrievalError, index_document
    c = indexed
    accepted = (await upload(c, b"Private content must stay local.\n")).json()
    await work(c, accepted["job_id"])
    await c["admin"].put(policy_path(c, "collection"), json={"expected_revision": 2, "approved_processor_ids": []}, headers=c["headers"])
    async def forbidden(bodies):
        pytest.fail("Unapproved content reached fake embedding")
    with pytest.raises(RetrievalError, match="awaiting_approval"):
        await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"],
            worker_engine=c["worker"], store=c["store"], embedder=forbidden)


async def test_bm25_uses_only_authorized_corpus_statistics(indexed):
    c = indexed
    await index(c, b"alpha alpha beta")
    await index(c, b"alpha gamma gamma gamma gamma gamma")
    await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    result = await retrieve(c, "alpha", lexical="bm25", actor=c["reader"])
    assert [hit["score"] for hit in result["lexical"]] == pytest.approx([0.2766258103, 0.16044296998])
    hidden = (await c["admin"].post(f'/api/v1/projects/{c["project"]}/collections', json={"name": "Unshared"}, headers=c["headers"])).json()["id"]
    # A private corpus must not change another user's IDF or length normalization.
    hidden_c = {**c, "collection": hidden}
    for kind in ("collection",):
        await c["admin"].put(policy_path(hidden_c, kind), json={"expected_revision": 1,
            "approved_processor_ids": ["test:gemini:embedding:v1"]}, headers=c["headers"])
    await index(hidden_c, b"alpha " * 500)
    again = await retrieve(c, "alpha", lexical="bm25", actor=c["reader"])
    assert [hit["score"] for hit in again["lexical"]] == [hit["score"] for hit in result["lexical"]]


async def test_exact_and_hnsw_have_distinct_real_plans_and_same_scope(indexed):
    c = indexed
    await index(c, b"Alpha connection setup.\n")
    await index(c, b"Beta unrelated material.\n")
    exact = await retrieve(c, "connection", vector="exact", explain=True)
    ann = await retrieve(c, "connection", vector="hnsw", explain=True)
    assert [hit["chunk_id"] for hit in exact["vector"]] == [hit["chunk_id"] for hit in ann["vector"]]
    assert "ix_chunks_embedding_hnsw" not in json.dumps(exact["plans"]["vector"])
    assert "ix_chunks_embedding_hnsw" in json.dumps(ann["plans"]["vector"])
    assert ann["settings"]["hnsw.iterative_scan"] == "strict_order"
    assert len(ann["vector"]) == 2


async def test_old_versions_and_deleted_documents_disappear_from_both_channels(indexed):
    from docweave.retrieval import index_document
    c = indexed
    accepted = await index(c, b"Original alpha instructions.\n")
    replaced = (await upload(c, b"New beta instructions.\n", accepted["document_id"])).json()
    await work(c, replaced["job_id"])
    await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"], worker_engine=c["worker"], store=c["store"], embedder=fake_vectors)
    old = await retrieve(c, "alpha")
    assert old["lexical"] == [] and old["vector"][0]["quote"] == "New beta instructions.\n"
    assert (await c["admin"].delete(f'/api/v1/documents/{accepted["document_id"]}', headers=c["headers"])).status_code == 202
    deleted = await retrieve(c, "alpha", lexical="bm25", vector="hnsw")
    assert deleted["lexical"] == [] and deleted["vector"] == []
    async with c["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.chunks")) == 0


async def test_generation_isolation_never_falls_back_to_another_embedding_space(indexed):
    from docweave.retrieval import RetrievalError
    c = indexed
    await index(c, b"Alpha source.\n")
    other = uuid4()
    async with c["owner"].begin() as connection:
        await connection.execute(text("""INSERT INTO app.index_generations(id,model,backend,dimensions,normalization,chunker,processor_ids,enabled)
            SELECT :other,'test-other-space',backend,dimensions,normalization,chunker,processor_ids,true FROM app.index_generations WHERE id=:current"""),
            {"other": other, "current": c["generation"]})
    result = await retrieve(c, "alpha", generation=other)
    assert result["lexical"] == [] and result["vector"] == []
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.index_generations SET enabled=false WHERE id=:id"), {"id": c["generation"]})
    with pytest.raises(RetrievalError, match="generation_unavailable"):
        await retrieve(c, "alpha")


async def test_permission_revocation_during_embedding_fences_index_publication(indexed):
    from docweave.retrieval import RetrievalError, index_document
    c = indexed
    accepted = (await upload(c, b"Private alpha data.\n")).json()
    await work(c, accepted["job_id"])
    async def revoke(bodies):
        assert bodies == ["Private alpha data.\n"]
        await c["admin"].put(policy_path(c, "collection"), json={"expected_revision": 2, "approved_processor_ids": []}, headers=c["headers"])
        return [basis()]
    with pytest.raises(RetrievalError, match="awaiting_approval"):
        await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"], worker_engine=c["worker"], store=c["store"], embedder=revoke)
    async with c["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.chunks")) == 0


async def test_source_approval_tracks_selected_version_but_survives_goal_edits(indexed):
    from test_sources import approved_selection, import_source
    from docweave.retrieval import index_document
    c = indexed
    selection = await approved_selection(c)
    accepted = (await import_source(c, selection)).json()
    async def frozen(stored):
        return b"# Alpha\n\nApproved documentation.\n", "text/markdown"
    await work(c, accepted["job_id"], fetcher=frozen)
    async with c["owner"].connect() as connection:
        document = await connection.scalar(text("SELECT document_id FROM app.ingestion_jobs WHERE id=:id"), {"id": UUID(accepted["job_id"])})
    await index_document(c["actor"], document, c["generation"], worker_engine=c["worker"], store=c["store"], embedder=fake_vectors)
    assert (await retrieve(c, "alpha"))["lexical"]
    path = f'/api/v1/projects/{c["project"]}'
    assert (await c["admin"].patch(path, json={"expected_revision": 1, "goal": "Updated goal"}, headers=c["headers"])).status_code == 200
    assert (await retrieve(c, "alpha"))["lexical"]
    assert (await c["admin"].patch(path, json={"expected_revision": 2, "stack": [{"technology": "FastAPI", "docs_target": "different-version"}]}, headers=c["headers"])).status_code == 200
    result = await retrieve(c, "alpha", lexical="bm25", vector="hnsw")
    assert result["lexical"] == [] and result["vector"] == []


async def test_revocation_before_result_release_removes_captured_evidence(indexed, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from docweave import retrieval
    c = indexed
    await index(c, b"Private alpha evidence.\n")
    original, revoked = AsyncSession.execute, False
    async def revoke_after_query(session, statement, *args, **kwargs):
        nonlocal revoked
        result = await original(session, statement, *args, **kwargs)
        if session.bind is c["runtime"] and str(statement) == retrieval.EXACT and not revoked:
            revoked = True
            await c["admin"].put(policy_path(c, "collection"), json={"expected_revision": 2, "approved_processor_ids": []}, headers=c["headers"])
        return result
    monkeypatch.setattr(AsyncSession, "execute", revoke_after_query)
    with pytest.raises(retrieval.RetrievalError, match="scope_changed"):
        await retrieve(c, "alpha")


async def test_raw_chunk_rls_requires_an_explicit_current_generation(indexed):
    from docweave.db import tenant_session
    c = indexed
    await index(c, b"Alpha protected corpus.\n")
    async with tenant_session(c["runtime"], actor_id=c["actor"].user_id, workspace_id=c["actor"].workspace_id) as session:
        assert await session.scalar(text("SELECT count(*) FROM app.chunks")) == 0
        await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(c["generation"])})
        assert await session.scalar(text("SELECT count(*) FROM app.chunks")) == 1
        await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(uuid4())})
        assert await session.scalar(text("SELECT count(*) FROM app.chunks")) == 0
    async with c["runtime"].connect() as connection:
        assert not await connection.scalar(text("SELECT current_setting('docweave.generation_id',true)"))


async def test_wrong_tenant_cannot_index_and_runtime_cannot_forge_chunks(indexed):
    from docweave.policy import Actor
    from docweave.db import tenant_session
    from docweave.retrieval import RetrievalError, index_document
    c = indexed
    accepted = (await upload(c)).json()
    await work(c, accepted["job_id"])
    async def forbidden(bodies):
        pytest.fail("Another tenant's text reached embedding")
    with pytest.raises(RetrievalError, match="not_found"):
        await index_document(Actor(B, WB), UUID(accepted["document_id"]), c["generation"], worker_engine=c["worker"], store=c["store"], embedder=forbidden)
    with pytest.raises(DBAPIError) as error:
        async with tenant_session(c["runtime"], actor_id=c["actor"].user_id, workspace_id=c["actor"].workspace_id) as session:
            await session.execute(text("DELETE FROM app.chunks"))
    assert error.value.orig.sqlstate == "42501"


async def test_failed_embedding_preserves_the_last_good_searchable_snapshot(indexed):
    from docweave.retrieval import index_document
    c = indexed
    accepted = await index(c, b"Original alpha evidence.\n")
    before = await retrieve(c, "alpha")
    old_chunk = before["lexical"][0]["chunk_id"]
    replacement = (await upload(c, b"Replacement beta evidence.\n", accepted["document_id"])).json()
    await work(c, replacement["job_id"])
    assert (await retrieve(c, "alpha"))["lexical"][0]["chunk_id"] == old_chunk
    assert (await metadata(c, accepted))["status"] == "stale"
    async def fail(bodies):
        raise OSError("Embedding failed")
    with pytest.raises(OSError):
        await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"], worker_engine=c["worker"], store=c["store"], embedder=fail)
    assert (await retrieve(c, "alpha"))["lexical"][0]["chunk_id"] == old_chunk


async def test_return_to_a_retained_version_reuses_vectors_and_reactivates_it(indexed):
    from docweave.retrieval import index_document
    c = indexed
    first = await index(c, b"Original alpha.\n")
    original = (await retrieve(c, "alpha"))["lexical"][0]["chunk_id"]
    for content in (b"Replacement beta.\n", b"Original alpha.\n"):
        accepted = (await upload(c, content, first["document_id"])).json()
        await work(c, accepted["job_id"])
        async def forbidden(bodies):
            pytest.fail("Retained compatible vectors were embedded again")
        await index_document(c["actor"], UUID(first["document_id"]), c["generation"], worker_engine=c["worker"], store=c["store"],
            embedder=forbidden if b"alpha" in content else fake_vectors)
    assert (await retrieve(c, "alpha"))["lexical"][0]["chunk_id"] == original


async def test_oversized_integer_vectors_use_the_documented_validation_error():
    from docweave.retrieval import RetrievalError, vector_literal
    with pytest.raises(RetrievalError, match="invalid_vector"):
        vector_literal([10**400] + [0] * 767)
