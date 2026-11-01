"""Sync retries queue durable metadata work without recreating chats or answers."""
import asyncio
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text

from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine

pytestmark = pytest.mark.anyio


async def test_sync_retry_migration_roundtrip_preserves_rows_and_role_grants(databases, test_urls):
    from tests.database.test_database import migrate
    from docweave.repositories.ownership import preservation_snapshot
    owner, _ = databases
    async with owner.begin() as connection:
        before = await preservation_snapshot(connection)
    await migrate(test_urls[1], '0027_personal_source_scope', downgrade=True)
    await migrate(test_urls[1], 'head')
    await owner.dispose()
    async with owner.begin() as connection:
        assert await preservation_snapshot(connection) == before
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_runtime','app.personal_retry_sync(uuid)','EXECUTE')")) is True
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_worker','app.personal_retry_sync(uuid)','EXECUTE')")) is False


async def test_blocked_chat_retry_is_async_deduplicated_and_authorized(github_login):
    from docweave.main import create_app
    settings, runtime, owner, github, state, cookie, _, _ = github_login
    async def repository(token, identity):
        return {'id': identity, 'name': 'repo', 'default_branch': 'main'}
    async def head(*args):
        return 'a' * 40
    github.repository, github.head = repository, head
    app = create_app(github_settings=settings, auth_engine=runtime, github_client=github)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url=settings.origin) as client:
        client.cookies.set('docweave_session', cookie)
        me = (await client.get('/api/v1/me')).json()
        headers = {'Origin': settings.origin, 'X-CSRF-Token': me['csrf_token']}
        project = (await client.post('/api/v1/projects', json={'repository_id': 42, 'goal': 'Help'}, headers=headers)).json()
        chat = (await client.post(f"/api/v1/projects/{project['id']}/conversations", json={}, headers=headers)).json()
        path = f"/api/v1/conversations/{chat['id']}/sync-retry"
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.personal_jobs SET status='completed' WHERE conversation_id=CAST(:id AS uuid)"), {'id': chat['id']})
            await connection.execute(text("UPDATE app.conversations SET status='blocked' WHERE id=CAST(:id AS uuid)"), {'id': chat['id']})
        assert (await client.post(path, json={})).status_code == 403
        responses = await asyncio.gather(*(client.post(path, json={}, headers=headers) for _ in range(2)))
        assert [r.status_code for r in responses] == [202, 202]
        assert all(r.json()['id'] == chat['id'] and r.json()['status'] == 'initializing' for r in responses)
        async with owner.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid) AND status='queued'"), {'id': chat['id']}) == 1
            assert await connection.scalar(text('SELECT count(*) FROM app.turns')) == 0
            assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls')) == 0
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.projects SET owner_user_id=:other WHERE id=CAST(:id AS uuid)"), {'other': UUID('00000000-0000-4000-8000-000000000002'), 'id': project['id']})
        assert (await client.post(path, json={}, headers=headers)).status_code == 404
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.projects SET owner_user_id=CAST(:actor AS uuid) WHERE id=CAST(:id AS uuid)"), {'actor': me['id'], 'id': project['id']})
        assert (await client.delete(f"/api/v1/conversations/{chat['id']}", headers=headers)).status_code == 204
        assert (await client.post(path, json={}, headers=headers)).status_code == 404


async def test_partial_sync_preserves_good_memory_and_retry_rechecks_commit(github_login, monkeypatch):
    from docweave.integrations.stack import parse_stack
    from docweave.services.github_auth import session_context
    from docweave.services.personal_worker import run_personal_job
    from docweave.repositories import personal
    from docweave.db.sessions import domain_session
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    actor = UUID(user['id'])
    async def repository(token, identity):
        return {'id': identity, 'name': 'repo', 'default_branch': 'main'}
    client.repository = repository
    async with domain_session(runtime, actor) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    old_stack = [{'id': 'react', 'technology': 'react', 'ecosystem': 'javascript', 'role': 'runtime'}]
    async with owner.begin() as connection:
        import json
        await connection.execute(text("UPDATE app.projects SET last_commit_sha=:sha,context_revision=5,stack=CAST(:stack AS jsonb),stack_fingerprint='old' WHERE id=CAST(:id AS uuid)"),
            {'id': project['id'], 'sha': 'b' * 40, 'stack': json.dumps(old_stack)})
        job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid)'), {'id': chat['id']})
    seen = []
    async def scan(*args, **kwargs):
        seen.append(kwargs['previous_commit'])
        return {'commit_sha': 'a' * 40, 'scan': parse_stack({'package.json': b'['} if len(seen) == 1 else {'package.json': b'{"dependencies":{"react":"^19"}}'}), 'unchanged': False}
    monkeypatch.setattr('docweave.services.personal_worker.scan_repository', scan)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        await run_personal_job(job, engine=worker, settings=settings, client=client)
        async with domain_session(runtime, actor) as session:
            blocked = await personal.conversation(session, UUID(chat['id']))
            assert blocked['status'] == 'blocked'
            assert 'metadata' in blocked['progress'].lower()
            preserved = await personal.project(session, UUID(project['id']))
            assert preserved['stack'] == old_stack and preserved['context_revision'] == 5
            assert preserved['repository']['commit_sha'] == 'b' * 40
            await personal.retry_sync(session, UUID(chat['id']))
        async with owner.connect() as connection:
            retry = await connection.scalar(text("SELECT id FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid) AND status='queued'"), {'id': chat['id']})
        await run_personal_job(retry, engine=worker, settings=settings, client=client)
        async with domain_session(runtime, actor) as session:
            ready = await personal.conversation(session, UUID(chat['id']))
            current = await personal.project(session, UUID(project['id']))
            assert ready['status'] == 'ready' and ready['progress'] is None
            assert current['repository']['commit_sha'] == 'a' * 40
            assert current['context_revision'] == 6
            assert seen == ['b' * 40, 'b' * 40]
    finally:
        await worker.dispose()


async def test_concurrent_sync_jobs_refresh_context_after_project_lock(github_login, monkeypatch):
    from docweave.integrations.stack import parse_stack
    from docweave.services.github_auth import session_context
    from docweave.services.personal_worker import run_personal_job
    from docweave.repositories import personal
    from docweave.db.sessions import domain_session
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    actor = UUID(user['id'])
    async def repository(token, identity):
        return {'id': identity, 'name': 'repo', 'default_branch': 'main'}
    client.repository = repository
    async with domain_session(runtime, actor) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        for _ in range(2):
            await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.connect() as connection:
        jobs = list((await connection.execute(text('SELECT id FROM app.personal_jobs ORDER BY created_at,id'))).scalars())
    entered, release = asyncio.Event(), asyncio.Event()
    seen = []
    async def scan(*args, **kwargs):
        seen.append(kwargs['previous_commit'])
        if len(seen) == 1:
            entered.set()
            await release.wait()
        # Same dependency facts after a force-push must not increment context again.
        return {'commit_sha': ('a' if len(seen) == 1 else 'b') * 40,
            'scan': parse_stack({'package.json': b'{"dependencies":{"react":"^19"}}'}), 'unchanged': False}
    monkeypatch.setattr('docweave.services.personal_worker.scan_repository', scan)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    first = asyncio.create_task(run_personal_job(jobs[0], engine=worker, settings=settings, client=client))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(run_personal_job(jobs[1], engine=worker, settings=settings, client=client))
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 10)
        assert seen == [None, 'a' * 40]
        async with domain_session(runtime, actor) as session:
            current = await personal.project(session, UUID(project['id']))
            assert current['context_revision'] == 2
            assert current['repository']['commit_sha'] == 'b' * 40
        async with owner.connect() as connection:
            assert list((await connection.execute(text('SELECT status FROM app.conversations'))).scalars()) == ['ready', 'ready']
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)
        await worker.dispose()


async def test_stale_sync_publication_reports_rejected_without_overwriting_memory(github_login):
    from docweave.services.github_auth import session_context
    from docweave.repositories import personal
    from docweave.db.sessions import domain_session
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    async with domain_session(runtime, UUID(user['id'])) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.connect() as connection:
        job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid)'), {'id': chat['id']})
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        async with worker.begin() as connection:
            claimed = await personal.claim_job(connection, job)
        async with worker.begin() as connection:
            assert await personal.finish_job(connection, job, UUID(claimed['lease_token']), {'status': 'ready',
                'expected_revision': 0, 'context_revision': 1, 'stack': [], 'stack_fingerprint': 'stale', 'last_commit_sha': 'a' * 40}) is False
        async with domain_session(runtime, UUID(user['id'])) as session:
            current = await personal.project(session, UUID(project['id']))
            assert current['context_revision'] == 1 and current['repository']['commit_sha'] is None
            assert (await personal.conversation(session, UUID(chat['id'])))['status'] == 'blocked'
    finally:
        await worker.dispose()
