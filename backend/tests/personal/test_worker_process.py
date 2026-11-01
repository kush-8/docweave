"""Kill an actual queue worker, then recover after startup while it stays running."""
import asyncio
import os
import subprocess
import sys
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls  # noqa: F401
from tests.paths import REPO_ROOT
from docweave.core.settings import database_url
from docweave.db.sessions import domain_session
from docweave.repositories import personal
from docweave.services.github_auth import session_context

pytestmark = pytest.mark.anyio


async def test_killed_worker_recovers_original_job_after_lease_expires_post_restart(github_login, tmp_path):
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    async with domain_session(runtime, UUID(user['id'])) as session:
        project = await personal.create_project(session, {'name': 'Fixture', 'goal': 'Kill/restart acceptance', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.connect() as connection:
        job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE conversation_id=CAST(:id AS uuid)'), {'id': chat['id']})
    sentinel = tmp_path / 'leased'
    environment = {**os.environ, 'APP_ORIGIN': settings.origin, 'GITHUB_CLIENT_ID': 'fixture',
        'GITHUB_CLIENT_SECRET': 'fixture', 'AUTH_ENCRYPTION_KEY': settings.encryption_key,
        'AUTH_LOCALHOST_HTTP': 'false', 'GITHUB_APP_SLUG': '', 'GROQ_API_KEY': '', 'GEMINI_API_KEY': '',
        'RAG_GENERATION_ID': '', 'DATABASE_URL': database_url('TEST_DATABASE_URL').render_as_string(hide_password=False),
        'WORKER_DATABASE_URL': database_url('TEST_WORKER_DATABASE_URL').render_as_string(hide_password=False),
        'PYTHONPATH': os.pathsep.join((str(REPO_ROOT / 'backend/src'), str(REPO_ROOT / 'backend'))),
        'RECOVERY_TEST_MODE': 'pause', 'RECOVERY_TEST_SENTINEL': str(sentinel)}
    children = []
    async def wait_for(predicate, timeout=15):
        async with asyncio.timeout(timeout):
            while not await predicate():
                assert all(child.poll() is None for child in children), 'Acceptance child exited; inspect its private test log'
                await asyncio.sleep(0.1)
    async def paused():
        return sentinel.exists()
    async def state(query):
        async with owner.connect() as connection:
            return await connection.scalar(text(query), {'id': job})
    async def original_delivery_done():
            return await state("SELECT EXISTS(SELECT 1 FROM queue.procrastinate_jobs WHERE args->>'job_id'=CAST(CAST(:id AS uuid) AS text) AND status='succeeded')")
    async def completed():
        return await state("SELECT status='completed' FROM app.personal_jobs WHERE id=:id")
    with (tmp_path / 'worker.log').open('wb') as log:
        def start():
            child = subprocess.Popen([sys.executable, '-m', 'tests.support.recovery_process'], cwd=REPO_ROOT,
                env=environment, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            children.append(child)
            return child
        try:
            first = start()
            await wait_for(paused)
            assert await state("SELECT status='running' FROM app.personal_jobs WHERE id=:id")
            first.kill()
            await asyncio.to_thread(first.wait, 5)
            children.remove(first)
            # Use actual queue heartbeat expiry; age only the ten-minute application lease.
            await asyncio.sleep(32)
            async with owner.begin() as connection:
                await connection.execute(text("UPDATE app.personal_jobs SET lease_expires_at=now()+interval '5 seconds' WHERE id=:id"), {'id': job})
            environment['RECOVERY_TEST_MODE'] = 'resume'
            start()
            await wait_for(original_delivery_done)
            assert await state("SELECT status='running' FROM app.personal_jobs WHERE id=:id")
            await wait_for(completed, timeout=25)
            async with owner.connect() as connection:
                assert await connection.scalar(text('SELECT count(*) FROM app.personal_jobs WHERE id=:id'), {'id': job}) == 1
                assert await connection.scalar(text('SELECT context_revision FROM app.projects WHERE id=CAST(:id AS uuid)'), {'id': project['id']}) == 2
                assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls')) == 0
                assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == 0
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                await asyncio.to_thread(child.wait, 5)
