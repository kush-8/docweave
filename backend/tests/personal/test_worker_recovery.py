"""Interrupted work resumes its original intent and never revives deleted chats."""
import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.db.sessions import domain_session
from docweave.repositories import personal
from docweave.services.github_auth import session_context
from docweave.services.personal_worker import run_personal_job
from docweave.integrations.stack import parse_stack

pytestmark = pytest.mark.anyio


async def test_recovery_migrations_roundtrip_preserve_rows_and_restrict_runtime(databases, test_urls):
    from tests.database.test_database import migrate
    from docweave.repositories.ownership import preservation_snapshot
    owner, _ = databases
    async with owner.begin() as connection:
        before = await preservation_snapshot(connection)
    await migrate(test_urls[1], '0030_documentation_review', downgrade=True)
    await migrate(test_urls[1], 'head')
    await owner.dispose()
    async with owner.begin() as connection:
        assert await preservation_snapshot(connection) == before
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_runtime','app.personal_recover_jobs()','EXECUTE')")) is False
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_worker','app.personal_recover_jobs()','EXECUTE')")) is True


async def test_interrupted_sync_remains_recoverable_and_duplicate_delivery_finishes_once(github_login, monkeypatch):
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    async def repository(*args):
        return {'id': 42, 'name': 'repo', 'default_branch': 'main'}
    client.repository = repository
    async with domain_session(runtime, UUID(user['id'])) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.connect() as connection:
        job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid)'), {'id': chat['id']})
    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError
    monkeypatch.setattr('docweave.services.personal_worker.scan_repository', interrupted)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        with pytest.raises(asyncio.CancelledError):
            await run_personal_job(job, engine=worker, settings=settings, client=client)
        async with owner.begin() as connection:
            assert await connection.scalar(text('SELECT status FROM app.personal_jobs WHERE id=:id'), {'id': job}) == 'running'
            await connection.execute(text("UPDATE app.personal_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=:id"), {'id': job})
        async def scan(*args, **kwargs):
            return {'commit_sha': 'a' * 40, 'scan': parse_stack({'package.json': b'{}'}), 'unchanged': False}
        monkeypatch.setattr('docweave.services.personal_worker.scan_repository', scan)
        await asyncio.gather(*(run_personal_job(job, engine=worker, settings=settings, client=client) for _ in range(2)))
        async with owner.connect() as connection:
            assert await connection.scalar(text('SELECT status FROM app.personal_jobs WHERE id=:id'), {'id': job}) == 'completed'
            assert await connection.scalar(text('SELECT context_revision FROM app.projects WHERE id=CAST(:id AS uuid)'), {'id': project['id']}) == 2
            assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls')) == 0
    finally:
        await worker.dispose()


async def test_reconciliation_requeues_missing_delivery_once_and_ignores_deleted_chat(github_login):
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    async with domain_session(runtime, UUID(user['id'])) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.begin() as connection:
        await connection.execute(text('SET LOCAL search_path=queue,pg_catalog,app'))
        await connection.execute(text("UPDATE queue.procrastinate_jobs SET status='failed' WHERE task_name='docweave.personal'"))
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        async with worker.begin() as connection:
            assert await personal.recover_jobs(connection) == 1
            assert await personal.recover_jobs(connection) == 0
        async with domain_session(runtime, UUID(user['id'])) as session:
            await personal.delete_conversation(session, UUID(chat['id']))
        async with owner.begin() as connection:
            await connection.execute(text('SET LOCAL search_path=queue,pg_catalog,app'))
            await connection.execute(text("UPDATE queue.procrastinate_jobs SET status='failed' WHERE task_name='docweave.personal'"))
        async with worker.begin() as connection:
            assert await personal.recover_jobs(connection) == 0
    finally:
        await worker.dispose()


async def test_provider_response_recovery_reuses_charge_and_rechecks_consent(databases, monkeypatch):
    from tests.providers.test_budget import profile
    from tests.database.test_database import A, PA
    from docweave.services.personal_providers import dispatch
    from docweave.rag.contracts import HostedError
    owner, _ = databases
    identity = await profile(owner)
    async with owner.begin() as connection:
        await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:project'), {'actor': A, 'project': PA})
        for processor in ('test:budget:google', 'test:budget:groq'):
            await connection.execute(text('INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,:processor,:a)'), {'p': PA, 'processor': processor, 'a': A})
    requests = []
    async def transport(*args, **kwargs):
        requests.append(args)
        return {'answer': 'durable result', 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}
    async def authorize():
        pass
    monkeypatch.setattr('docweave.services.personal_providers.provider_post', transport)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    options = dict(embedding=False, profile_id=identity, operation_key='durable-job:resolution', actor_id=A,
        project_id=PA, engine=worker, api_key='fixture', authorize=authorize)
    payload = {'model': 'fake-model', 'max_completion_tokens': 10}
    try:
        first = await dispatch(payload, **options)
        assert await dispatch(payload, **options) == first
        assert len(requests) == 1
        async with owner.begin() as connection:
            assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == 1
            await connection.execute(text('DELETE FROM app.project_processor_approvals WHERE project_id=:p'), {'p': PA})
        with pytest.raises(HostedError):
            await dispatch(payload, **options)
        assert len(requests) == 1
    finally:
        await worker.dispose()


async def test_uncertain_provider_stage_is_not_replayed_even_after_request_changes(databases, monkeypatch):
    from tests.providers.test_budget import profile
    from tests.database.test_database import A, PA
    from docweave.services.personal_providers import dispatch
    from docweave.rag.contracts import HostedError
    owner, _ = databases
    identity = await profile(owner)
    async with owner.begin() as connection:
        await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:project'), {'actor': A, 'project': PA})
        for processor in ('test:budget:google', 'test:budget:groq'):
            await connection.execute(text('INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,:processor,:a)'), {'p': PA, 'processor': processor, 'a': A})
    requests = []
    async def transport(*args, **kwargs):
        requests.append(args)
        raise TimeoutError
    async def authorize():
        pass
    monkeypatch.setattr('docweave.services.personal_providers.provider_post', transport)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    options = dict(embedding=False, profile_id=identity, operation_key='original-job:resolution', actor_id=A,
        project_id=PA, engine=worker, api_key='fixture', authorize=authorize)
    try:
        for message in ('original context', 'changed context'):
            with pytest.raises(HostedError, match='completion_unknown'):
                await dispatch({'model': 'fake-model', 'max_completion_tokens': 10, 'message': message}, **options)
        assert len(requests) == 1
        async with owner.connect() as connection:
            assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == 1
            assert await connection.scalar(text('SELECT status FROM app.cost_reservations')) == 'uncertain'
    finally:
        await worker.dispose()


async def test_catalog_interruption_keeps_lease_recoverable(databases, tmp_path):
    from tests.database.test_public_catalog_schema import add_revision
    from docweave.rag.contracts import CONFIGURATION
    from docweave.services.shared_ingestion import run_catalog_job
    from docweave.storage.artifacts import ArtifactStore
    owner, _ = databases
    async with owner.begin() as connection:
        revision = await add_revision(connection, enabled=True, approved=True)
        generation = await connection.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES('fixture','fixture',768,'unit-l2',:config,'[\"fixture\"]',true) RETURNING id"), {'config': CONFIGURATION})
        job = await connection.scalar(text('INSERT INTO app.catalog_jobs(catalog_revision_id,generation_id) VALUES(:r,:g) RETURNING id'), {'r': revision, 'g': generation})
    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        with pytest.raises(asyncio.CancelledError):
            await run_catalog_job(job, engine=worker, store=ArtifactStore(tmp_path), fetcher=interrupted)
        async with owner.connect() as connection:
            assert await connection.scalar(text('SELECT status FROM app.catalog_jobs WHERE id=:id'), {'id': job}) == 'running'
    finally:
        await worker.dispose()
