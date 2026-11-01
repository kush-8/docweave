"""Late recovery cannot release stale context or retain deleted private replies."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import text
from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.db.sessions import domain_session
from docweave.repositories import personal
from docweave.services.github_auth import session_context

pytestmark = pytest.mark.anyio


async def test_late_answer_is_blocked_when_context_changed_after_generation(github_login):
    settings, runtime, owner, client, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, client, cookie)
    actor = UUID(user['id'])
    async with domain_session(runtime, actor) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"), {'id': chat['id']})
    async with domain_session(runtime, actor) as session:
        turn = await personal.append_turn(session, UUID(chat['id']), uuid4(), 'Explain this API')
    async with owner.connect() as connection:
        job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:id AS uuid)'), {'id': turn['id']})
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        async with worker.begin() as connection:
            claimed = await personal.claim_job(connection, job)
        async with owner.begin() as connection:
            await connection.execute(text('UPDATE app.projects SET context_revision=2 WHERE id=CAST(:id AS uuid)'), {'id': project['id']})
        async with worker.begin() as connection:
            await personal.finish_job(connection, job, UUID(claimed['lease_token']), {'status': 'completed', 'answer': 'stale answer', 'citations': [], 'expected_revision': 1})
        async with domain_session(runtime, actor) as session:
            result = await personal.turn(session, UUID(turn['id']))
            assert result['status'] == 'blocked_policy' and result['answer'] is None
    finally:
        await worker.dispose()
