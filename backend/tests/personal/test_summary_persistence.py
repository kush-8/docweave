"""Durable summaries exercise actual worker admission and PostgreSQL fences."""
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.db.sessions import domain_session
from docweave.repositories import personal
from docweave.services.answer_engine import AnswerEngine
from docweave.services.github_auth import session_context

pytestmark = pytest.mark.anyio


async def test_summary_persists_rebuilds_and_is_fenced_and_erased(github_login, monkeypatch):
    settings, runtime, owner, github, _, cookie, _, _ = github_login
    user, _ = await session_context(settings, runtime, github, cookie)
    actor = UUID(user['id'])
    async with domain_session(runtime, actor) as session:
        project = await personal.create_project(session, {'name': 'Repo', 'goal': 'Help', 'repository_id': 42, 'branch': 'main'})
        chat = await personal.create_conversation(session, UUID(project['id']), None)
    profile = uuid4()
    async with owner.begin() as c:
        await c.execute(text("UPDATE app.personal_jobs SET status='completed' WHERE conversation_id=CAST(:id AS uuid)"), {'id': chat['id']})
        await c.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"), {'id': chat['id']})
        await c.execute(text("""INSERT INTO app.processors(id,provider,backend,roles,enabled)
            VALUES('test:summary:groq','groq','fixture','["summarization"]',true)
            ON CONFLICT(id) DO UPDATE SET enabled=true"""))
        await c.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,
            input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,max_attempts,
            enabled,capabilities_verified,account_verified,pricing_verified)
            VALUES(:id,'groq','openai/gpt-oss-20b','fixture','summarization','["test:summary:groq"]',
            0,0,0,131072,4096,1,true,true,true,true)"""), {'id': profile})
        await c.execute(text("INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(CAST(:p AS uuid),'test:summary:groq',:actor)"), {'p': project['id'], 'actor': actor})
        for sequence in range(1, 4):
            await c.execute(text("""INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message,answer,status,context_revision)
                VALUES(CAST(:id AS uuid),:sequence,:key,:message,'Historical answer','completed',1)"""),
                {'id': chat['id'], 'sequence': sequence, 'key': uuid4(), 'message': 'Earlier discussion ' * 2500})
    async with domain_session(runtime, actor) as session:
        turn = await personal.append_turn(session, UUID(chat['id']), uuid4(), 'Continue the discussion')
    async with owner.connect() as c:
        job_id = await c.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:id AS uuid)'), {'id': turn['id']})
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    calls = []
    async def transport(embedding, encoded, key, **kwargs):
        calls.append(json.loads(encoded))
        return {'model': 'openai/gpt-oss-20b', 'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'summary': 'The user discussed earlier project goals on revision 1.'})}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post', transport)
    async def authorize():
        pass
    def pipeline(job):
        return AnswerEngine(job, engine=worker, read_engine=runtime,
            config={'SUMMARY_PROFILE_ID': str(profile), 'GROQ_API_KEY': 'placeholder'}, generation_id=None, authorize=authorize)
    try:
        async with worker.begin() as c:
            job = await personal.claim_job(c, job_id)
        first = await pipeline(job).context_history()
        count = len(calls)
        assert count > 0 and first[0]['summary']
        assert await pipeline(job).context_history() == first and len(calls) == count
        async with owner.connect() as c:
            saved = await c.scalar(text('SELECT summary FROM app.conversations WHERE id=CAST(:id AS uuid)'), {'id': chat['id']})
            assert saved['context_revision'] == 1
            assert saved['policy_epoch'] == 1
            assert await c.scalar(text("SELECT has_function_privilege('docweave_runtime','app.personal_worker_summary(uuid,uuid,integer,jsonb)','EXECUTE')")) is False
            assert await c.scalar(text('SELECT count(*) FROM app.personal_provider_calls WHERE response IS NOT NULL')) == count
        async with worker.begin() as c:
            assert await personal.summary(c, job_id, uuid4(), 1) is None
            assert await personal.summary(c, job_id, UUID(job['lease_token']), 2, saved) is None
            assert await personal.summary(c, job_id, UUID(job['lease_token']), 1, dict(saved, policy_epoch=0)) is None
        async with owner.begin() as c:
            await c.execute(text('UPDATE app.projects SET context_revision=2 WHERE id=CAST(:id AS uuid)'), {'id': project['id']})
        job['project']['context_revision'] = 2
        await pipeline(job).context_history()
        assert len(calls) > count
        async with domain_session(runtime, actor) as session:
            assert await personal.delete_conversation(session, UUID(chat['id']))
        async with worker.begin() as c:
            assert await personal.summary(c, job_id, UUID(job['lease_token']), 2, saved) is None
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT summary FROM app.conversations WHERE id=CAST(:id AS uuid)'), {'id': chat['id']}) is None
            assert await c.scalar(text('SELECT count(*) FROM app.personal_provider_calls WHERE response IS NOT NULL')) == 0
    finally:
        await worker.dispose()
