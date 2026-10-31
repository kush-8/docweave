"""Real ingestion behavior; external parsing/fetch transports are replaced only at IO."""

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_auth import auth_client  # noqa: F401
from test_collections import collections
from test_collections import replace_grants  # noqa: F401
from test_database import B
from test_database import WB
from test_database import databases
from test_database import test_urls  # noqa: F401
from test_memberships import members
from test_memberships import wait_for_lock  # noqa: F401

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


async def test_text_normalization_chunks_and_exact_locators():
    from docweave.rag.parsing import parse_text

    parsed = parse_text(b"\xef\xbb\xbf# Connection\r\n\r\nUse PostgreSQL.\r\n", "text/markdown")
    assert parsed["text"] == "# Connection\n\nUse PostgreSQL.\n"
    assert parsed["sha256"] == hashlib.sha256(b"# Connection\n\nUse PostgreSQL.\n").hexdigest()
    assert parsed["chunks"] == [{"start": 0, "end": 30, "heading": "Connection", "line_start": 1, "line_end": 3}]
    long = parse_text(("# Setup\n\n" + "word " * 850).encode(), "text/markdown")
    assert len(long["chunks"]) >= 3
    assert all(0 <= c["start"] < c["end"] <= len(long["text"]) for c in long["chunks"])
    assert long["chunks"][-1]["end"] == len(long["text"])
    assert all(a["end"] >= b["start"] for a, b in zip(long["chunks"], long["chunks"][1:]))


@pytest.mark.parametrize("content,media", [(b"\xff", "text/plain"), (b"a\x00b", "text/plain"), (b"   ", "text/plain"),
    (b"%PDF-1.7", "application/pdf"), (b"a" * 2_000_001, "text/plain")])
async def test_parser_rejects_invalid_binary_empty_or_overlong_content(content, media):
    from docweave.rag.parsing import parse_text
    with pytest.raises(ValueError):
        parse_text(content, media)


@pytest.fixture
async def ingestion(collections, tmp_path):
    from docweave.storage.artifacts import ArtifactStore
    from docweave.core.settings import database_url
    from docweave.db.engine import make_engine

    c = collections
    c["store"] = ArtifactStore(tmp_path / "private")
    c["data"]["app"].state.ingestion_store = c["store"]
    c["worker"] = make_engine(database_url("TEST_WORKER_DATABASE_URL"))
    try:
        yield c
    finally:
        await c["worker"].dispose()


async def upload(c, content=b"# Runbook\n\nUse SCRAM authentication.\n", document=None, client=None, headers=None):
    path = f'/api/v1/documents/{document}/versions' if document else f'/api/v1/collections/{c["collection"]}/documents'
    return await (client or c["admin"]).post(path, files={"file": ("runbook.md", content, "text/markdown")}, headers=headers or c["headers"])


async def work(c, job, **kwargs):
    from docweave.services.ingestion import run_ingestion
    from docweave.rag.parsing import parse_text
    return await run_ingestion(UUID(job), engine=c["worker"], store=c["store"], parser=parse_text, **kwargs)


async def metadata(c, accepted):
    return (await c["admin"].get(f'/api/v1/documents/{accepted["document_id"]}')).json()


async def test_upload_commits_metadata_and_queue_together_and_prepares_snapshot(ingestion):
    c = ingestion
    response = await upload(c)
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["request_id"] == response.headers["X-Request-ID"]
    queued = await c["admin"].get(accepted["status_url"])
    assert queued.status_code == 200 and queued.json()["status"] == "queued"
    async with c["owner"].connect() as connection:
        args = await connection.scalar(text("SELECT args FROM queue.procrastinate_jobs"))
        assert args == {"job_id": accepted["job_id"]}
    assert "SCRAM" not in queued.text and "storage" not in queued.text
    await work(c, accepted["job_id"])
    document = await metadata(c, accepted)
    assert document["status"] == "awaiting_approval"
    versions = await c["admin"].get(f'/api/v1/documents/{accepted["document_id"]}/versions')
    assert versions.status_code == 200
    assert len(versions.json()["items"]) == 1 and versions.json()["items"][0]["active"]
    assert document["active_version_id"] == versions.json()["items"][0]["id"]
    assert (await c["admin"].get(accepted["status_url"])).json()["stage"] == "snapshot_published"
    listing = await c["admin"].get(f'/api/v1/collections/{c["collection"]}/documents')
    assert listing.json()["items"] == [document]


async def test_duplicate_content_and_repeated_delivery_do_not_create_versions(ingestion):
    c = ingestion
    first = (await upload(c)).json()
    duplicate = (await upload(c)).json()
    assert first["document_id"] == duplicate["document_id"] and first["job_id"] == duplicate["job_id"]
    await work(c, first["job_id"])
    await work(c, first["job_id"])
    replacement = (await upload(c, b"\xef\xbb\xbf# Runbook\r\n\r\nUse SCRAM authentication.\r\n", first["document_id"])).json()
    await work(c, replacement["job_id"])
    versions = (await c["admin"].get(f'/api/v1/documents/{first["document_id"]}/versions')).json()["items"]
    assert len(versions) == 1


async def test_failed_replacement_preserves_last_good_snapshot(ingestion):
    c = ingestion
    first = (await upload(c)).json()
    await work(c, first["job_id"])
    active = (await metadata(c, first))["active_version_id"]
    bad = (await upload(c, b"invalid\x00content", first["document_id"])).json()
    await work(c, bad["job_id"])
    assert (await metadata(c, first))["active_version_id"] == active
    assert (await metadata(c, first))["status"] == "stale"
    status = (await c["admin"].get(bad["status_url"])).json()
    assert status["status"] == "failed" and status["retryable"] is False
    assert "invalid" not in json.dumps(status)


async def test_revoked_writer_never_reaches_parser_and_cannot_read_jobs(ingestion):
    c = ingestion
    user = c["recipient"]["id"]
    member = f'/api/v1/workspaces/{c["workspace"]["id"]}/members/{user}'
    await c["admin"].patch(member, json={"role": "maintainer"}, headers=c["headers"])
    await replace_grants(c, [{"user_id": user, "access": "write"}])
    accepted = (await upload(c, client=c["guest"], headers=c["guest_headers"])).json()
    await replace_grants(c, [], revision=2)
    def forbidden(*args):
        pytest.fail("Revoked private text reached processing")
    from docweave.services.ingestion import run_ingestion
    await run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=forbidden)
    assert (await c["guest"].get(accepted["status_url"])).status_code == 404
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "blocked_policy"


async def test_deletion_during_processing_fences_publication_and_removes_bytes(ingestion):
    c = ingestion
    accepted = (await upload(c)).json()
    from docweave.services.ingestion import run_ingestion
    from docweave.rag.parsing import parse_text
    started, resume = asyncio.Event(), asyncio.Event()
    async def paused(content, media):
        started.set()
        await resume.wait()
        return parse_text(content, media)
    task = asyncio.create_task(run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=paused))
    try:
        await asyncio.wait_for(started.wait(), 5)
        deleted = await c["admin"].delete(f'/api/v1/documents/{accepted["document_id"]}', headers=c["headers"])
        assert deleted.status_code == 202, deleted.text
        resume.set()
        await task
    finally:
        resume.set()
        await task
    assert (await c["admin"].get(f'/api/v1/documents/{accepted["document_id"]}')).status_code == 404
    async with c["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.document_versions")) == 0
    assert list(c["store"].root.iterdir()) == []


async def test_current_read_grant_controls_document_versions_and_jobs(ingestion):
    c = ingestion
    accepted = (await upload(c)).json()
    await work(c, accepted["job_id"])
    paths = [accepted["status_url"], f'/api/v1/documents/{accepted["document_id"]}', f'/api/v1/documents/{accepted["document_id"]}/versions']
    for path in paths:
        assert (await c["guest"].get(path)).status_code == 404
    await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    for path in paths:
        assert (await c["guest"].get(path)).status_code == 200
    assert (await upload(c, client=c["guest"], headers=c["guest_headers"])).status_code == 403
    assert (await c["guest"].delete(paths[1], headers=c["guest_headers"])).status_code == 403


async def test_upload_rejects_unknown_parts_and_unsupported_types_without_artifacts(ingestion):
    c = ingestion
    path = f'/api/v1/collections/{c["collection"]}/documents'
    for files in [{"file": ("x.pdf", b"%PDF", "application/pdf")},
        [("file", ("a.txt", b"ok", "text/plain")), ("file", ("b.txt", b"no", "text/plain"))],
        {"file": ("x.txt", b"", "text/plain"), "scope": (None, "trusted")},
        {"file": ("../x.md", b"ok", "text/markdown")}]:
        response = await c["admin"].post(path, files=files, headers=c["headers"])
        assert response.status_code == 422, response.text
    assert list(c["store"].root.iterdir()) == []


async def test_runtime_has_no_queue_or_artifact_write_authority(ingestion):
    c = ingestion
    from docweave.db.sessions import tenant_session
    for sql in ["SELECT * FROM queue.procrastinate_jobs", "UPDATE app.documents SET title='forged'", "SELECT * FROM app.document_versions"]:
        with pytest.raises(DBAPIError) as error:
            async with tenant_session(c["runtime"], actor_id=UUID(c["user"]["id"]), workspace_id=UUID(c["workspace"]["id"])) as session:
                await session.execute(text(sql))
        assert error.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("anyio_backend", [("asyncio", {"loop_factory": asyncio.SelectorEventLoop})])
async def test_real_queue_worker_drains_a_job_without_an_in_process_task(ingestion):
    c = ingestion
    accepted = (await upload(c)).json()
    from docweave.workers.ingestion import run_worker
    from docweave.core.settings import database_url
    from docweave.rag.parsing import parse_text
    await run_worker(database_url("TEST_WORKER_DATABASE_URL"), c["store"], wait=False, parser=parse_text)
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "completed"
    async with c["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT status::text FROM queue.procrastinate_jobs")) == "succeeded"


async def test_worker_attempts_are_bounded_and_expired_leases_fence_old_publication(ingestion):
    c = ingestion
    accepted = (await upload(c)).json()
    async with c["worker"].begin() as connection:
        first = await connection.scalar(text("SELECT app.claim_ingestion(:id)"), {"id": UUID(accepted["job_id"])})
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second'"))
    async with c["worker"].begin() as connection:
        second = await connection.scalar(text("SELECT app.claim_ingestion(:id)"), {"id": UUID(accepted["job_id"])})
        assert second["token"] != first["token"]
        assert await connection.scalar(text("SELECT app.publish_ingestion(:id,:token,:version,:hash,:config)"),
            {"id": UUID(accepted["job_id"]), "token": UUID(first["token"]), "version": uuid4(), "hash": "a" * 64,
                "config": "utf8-lf:headings:whitespace350-overlap50:v1"}) is None
        await connection.execute(text("SELECT app.fail_ingestion(:id,:token,true)"), {"id": UUID(accepted["job_id"]), "token": UUID(second["token"])})
    async def transient(*args):
        raise OSError("Temporary parser failure")
    from docweave.services.ingestion import run_ingestion
    with pytest.raises(OSError):
        await run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=transient)
    await run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=transient)
    status = (await c["admin"].get(accepted["status_url"])).json()
    assert status["attempts"] == 3 and status["status"] == "failed" and not status["retryable"]


async def test_container_parser_runs_the_same_bounded_parser():
    from docweave.integrations.parser import container_parse
    parsed = await container_parse(b"# Container\n\nNo network or private mounts.\n", "text/markdown")
    assert parsed["text"] == "# Container\n\nNo network or private mounts.\n"
    with pytest.raises(ValueError):
        await container_parse(b"\x00", "text/plain")


async def test_frozen_official_and_synthetic_fixtures_have_stable_exact_spans():
    from docweave.rag.parsing import parse_text
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert len(manifest["documents"]) == 3
    for document in manifest["documents"]:
        raw = (FIXTURES / document["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == document["sha256"]
        parsed = parse_text(raw, document["media_type"])
        assert parsed["chunks"]
        for chunk in parsed["chunks"]:
            assert parsed["text"][chunk["start"]:chunk["end"]].strip()
    assert manifest["documents"][1]["coverage"]["granularity"] == "rolling"
    assert manifest["documents"][2]["coverage"]["publisher_range"] == "17"


async def test_upload_rechecks_authority_after_workspace_lock_and_removes_uncommitted_bytes(ingestion):
    c = ingestion
    task = None
    try:
        async with c["owner"].begin() as connection, c["runtime"].connect() as observer:
            await connection.execute(text("SELECT id FROM app.workspaces WHERE id=:id FOR UPDATE"), {"id": UUID(c["workspace"]["id"])})
            task = asyncio.create_task(upload(c))
            await wait_for_lock(observer, "enqueue_ingestion")
            await connection.execute(text("UPDATE app.memberships SET role='member' WHERE workspace_id=:w AND user_id=:actor"),
                {"w": UUID(c["workspace"]["id"]), "actor": UUID(c["user"]["id"])})
        response = await task
        assert response.status_code == 404
        assert list(c["store"].root.iterdir()) == []
        async with c["owner"].connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM app.ingestion_jobs")) == 0
            assert await connection.scalar(text("SELECT count(*) FROM queue.procrastinate_jobs")) == 0
    finally:
        if task is not None:
            await task


async def test_lost_commit_confirmation_does_not_remove_a_durable_upload(ingestion, monkeypatch):
    c = ingestion
    from docweave.services import ingestion as module
    session = module.domain_session
    @asynccontextmanager
    async def uncertain_commit(*args, **kwargs):
        async with session(*args, **kwargs) as active:
            yield active
        raise OSError("Commit acknowledgement lost")
    monkeypatch.setattr(module, "domain_session", uncertain_commit)
    assert (await upload(c)).status_code == 500
    monkeypatch.setattr(module, "domain_session", session)
    async with c["owner"].connect() as connection:
        job = await connection.scalar(text("SELECT id FROM app.ingestion_jobs"))
    assert job is not None
    await work(c, str(job))
    assert (await c["admin"].get(f"/api/v1/jobs/{job}")).json()["status"] == "completed"


async def test_replacement_can_reactivate_an_older_immutable_snapshot(ingestion):
    c = ingestion
    first = (await upload(c, b"# A\nOriginal content.\n")).json()
    await work(c, first["job_id"])
    original = (await metadata(c, first))["active_version_id"]
    second = (await upload(c, b"# B\nReplacement content.\n", first["document_id"])).json()
    await work(c, second["job_id"])
    assert (await metadata(c, first))["active_version_id"] != original
    third = (await upload(c, b"# A\nOriginal content.\n", first["document_id"])).json()
    await work(c, third["job_id"])
    assert (await metadata(c, first))["active_version_id"] == original


async def test_parser_timeout_updates_durable_status_and_can_be_retried(ingestion, monkeypatch):
    c = ingestion
    from docweave.integrations.parser import container_parse
    from docweave.services.ingestion import run_ingestion
    accepted = (await upload(c)).json()
    def timeout(command, **kwargs):
        if "run" in command:
            raise subprocess.TimeoutExpired(command, 60)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(OSError):
        await run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=container_parse)
    status = (await c["admin"].get(accepted["status_url"])).json()
    assert status["status"] == "queued" and status["retryable"]
    await work(c, accepted["job_id"])
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "completed"


async def test_expired_publication_is_requeued_instead_of_silently_stranded(ingestion):
    c = ingestion
    from docweave.services.ingestion import run_ingestion
    from docweave.rag.parsing import parse_text
    accepted = (await upload(c)).json()
    async def expire(content, media):
        async with c["owner"].begin() as connection:
            await connection.execute(text("UPDATE app.ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second'"))
        return parse_text(content, media)
    with pytest.raises(OSError):
        await run_ingestion(UUID(accepted["job_id"]), engine=c["worker"], store=c["store"], parser=expire)
    status = (await c["admin"].get(accepted["status_url"])).json()
    assert status["status"] == "queued" and status["stage"] == "lease_expired"
    await work(c, accepted["job_id"])
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "completed"


async def test_replacement_media_type_changes_snapshot_identity_and_locators(ingestion):
    c = ingestion
    path = f'/api/v1/collections/{c["collection"]}/documents'
    content = b"# Heading\n\nSame bytes, different format.\n"
    first = (await c["admin"].post(path, files={"file": ("notes.txt", content, "text/plain")}, headers=c["headers"])).json()
    await work(c, first["job_id"])
    second = (await upload(c, content, first["document_id"])).json()
    await work(c, second["job_id"])
    document = await metadata(c, first)
    assert document["media_type"] == "text/markdown"
    versions = (await c["admin"].get(f'/api/v1/documents/{first["document_id"]}/versions')).json()["items"]
    assert len(versions) == 2
    parsed = json.loads(c["store"].read(document["active_version_id"]))
    assert parsed["chunks"][0]["heading"] == "Heading"


async def test_worker_cli_reads_the_configured_private_storage_root(ingestion):
    c = ingestion
    from docweave.core.paths import ROOT
    from docweave.core.settings import database_url
    accepted = (await upload(c)).json()
    environment = {**os.environ, "WORKER_DATABASE_URL": database_url("TEST_WORKER_DATABASE_URL").render_as_string(hide_password=False),
        "INGESTION_STORAGE_ROOT": str(c["store"].root), "PYTHONPATH": str(ROOT / "backend" / "src")}
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "docweave.worker", "--once"],
        env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "completed"


async def test_frozen_corpus_runs_through_upload_worker_and_private_artifacts(ingestion):
    c = ingestion
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for fixture in manifest["documents"]:
        response = await c["admin"].post(f'/api/v1/collections/{c["collection"]}/documents',
            files={"file": (fixture["file"], (FIXTURES / fixture["file"]).read_bytes(), fixture["media_type"])}, headers=c["headers"])
        assert response.status_code == 202
        accepted = response.json()
        await work(c, accepted["job_id"])
        document = await metadata(c, accepted)
        captured = json.loads(c["store"].read(document["active_version_id"]))
        assert captured["sha256"] == fixture["sha256"]
        assert len(captured["chunks"]) > 0


async def test_artifact_reconciliation_preserves_referenced_snapshots_and_removes_orphans(ingestion):
    c = ingestion
    from docweave.services.ingestion import reconcile_artifacts
    accepted = (await upload(c)).json()
    await work(c, accepted["job_id"])
    orphan = uuid4()
    c["store"].put(orphan, b"Unreferenced staged bytes")
    await reconcile_artifacts(c["worker"], c["store"], grace_seconds=0)
    assert not c["store"].path(orphan).exists()
    assert c["store"].path((await metadata(c, accepted))["active_version_id"]).exists()


async def test_markdown_chunks_preserve_headings_and_small_fenced_blocks():
    from docweave.rag.parsing import parse_text
    parsed = parse_text(b"# First\n\nAlpha.\n\n# Second\n\nBeta.\n", "text/markdown")
    assert [chunk["heading"] for chunk in parsed["chunks"]] == ["First", "Second"]
    parsed = parse_text(("# Setup\n\n" + "intro " * 340 + "\n\n```sql\n" + "SELECT " * 25 + ";\n```\n").encode(), "text/markdown")
    code = "```sql\n" + "SELECT " * 25 + ";\n```"
    assert any(code in parsed["text"][chunk["start"]:chunk["end"]] for chunk in parsed["chunks"])


async def test_parser_rejects_excessive_structure_without_unbounded_chunk_output():
    from docweave.rag.parsing import parse_text
    with pytest.raises(ValueError):
        parse_text(b"# Heading\n\nText.\n\n" * 10_001, "text/markdown")


async def test_uncertain_publication_preserves_a_committed_snapshot_artifact(ingestion, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncTransaction
    c = ingestion
    accepted = (await upload(c)).json()
    original_exit, interrupted = AsyncTransaction.__aexit__, False
    async def lost_ack(transaction, *args):
        nonlocal interrupted
        await original_exit(transaction, *args)
        if transaction.connection.engine is c["worker"] and not interrupted:
            async with c["owner"].connect() as connection:
                published = await connection.scalar(text("SELECT count(*) FROM app.document_versions"))
            if published:
                interrupted = True
                raise OSError("Publication confirmation lost")
    monkeypatch.setattr(AsyncTransaction, "__aexit__", lost_ack)
    with pytest.raises(OSError):
        await work(c, accepted["job_id"])
    active = (await metadata(c, accepted))["active_version_id"]
    assert c["store"].path(active).exists()


@pytest.mark.parametrize("anyio_backend", [("asyncio", {"loop_factory": asyncio.SelectorEventLoop})])
async def test_crashed_queue_delivery_recovers_after_its_application_lease_expires(ingestion):
    c = ingestion
    from docweave.workers.ingestion import run_worker
    from docweave.core.settings import database_url
    from docweave.rag.parsing import parse_text
    accepted = (await upload(c)).json()
    async with c["worker"].begin() as connection:
        assert await connection.scalar(text("SELECT app.claim_ingestion(:id)"), {"id": UUID(accepted["job_id"])})
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second'"))
        await connection.execute(text("SET LOCAL search_path=queue,pg_catalog,app"))
        await connection.execute(text("UPDATE queue.procrastinate_jobs SET status='doing',worker_id=NULL"))
    await run_worker(database_url("TEST_WORKER_DATABASE_URL"), c["store"], wait=False, parser=parse_text)
    status = (await c["admin"].get(accepted["status_url"])).json()
    assert status["status"] == "completed" and status["attempts"] == 2
