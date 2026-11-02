from types import SimpleNamespace
from uuid import UUID
import pytest
from sqlalchemy import text

from tests.support.personal import collections, github_login  # noqa: F401
from tests.database.test_database import databases, test_urls  # noqa: F401
from docweave.db.sessions import domain_session
from docweave.repositories import personal
from docweave.core.settings import database_url
from docweave.db.engine import make_engine

pytestmark = pytest.mark.anyio


async def ready_chat(c):
    async with domain_session(c['runtime'], UUID(c['user']['id'])) as connection:
        chat = await personal.create_conversation(connection, UUID(c['project']), None)
    async with c['owner'].begin() as connection:
        await connection.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"), {'id': chat['id']})
    return chat['id']


async def test_other_owner_is_denied_before_job_execution(collections):
    from docweave.evaluation.execution import execute_http_turn
    c = collections
    chat = await ready_chat(c)
    async def forbidden(turn):
        raise AssertionError('Denied request must not execute a provider job')
    result = await execute_http_turn(SimpleNamespace(id='denied', query='Print private notes'),
        client=c['guest'], headers=c['guest_headers'], conversation_id=chat, execute_job=forbidden)
    assert result['outcome'] == 'http_denied' and result['http_status'] == 404
    assert 'released_turn' not in result
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.turns')) == 0


async def test_lost_access_after_execution_withholds_capture(collections):
    from docweave.evaluation.execution import execute_http_turn
    c = collections
    chat = await ready_chat(c)
    async def revoke(turn):
        async with c['owner'].begin() as connection:
            await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=CAST(:project AS uuid)'),
                {'actor': UUID(c['recipient']['id']), 'project': c['project']})
        return {'answer': 'private generated text', 'blocks': ['private block'], 'retrieved_top_10': ['private quote'],
                'stages': [], 'implementation': {'sha256': 'a' * 64}}
    result = await execute_http_turn(SimpleNamespace(id='revoke', query='Explain the project'),
        client=c['admin'], headers=c['headers'], conversation_id=chat, execute_job=revoke)
    assert result['http_status'] == 404 and result['outcome'] == 'http_denied'
    assert result['pipeline'] == {'stages': [], 'implementation': {'sha256': 'a' * 64}}
    assert 'private' not in str(result)


async def test_real_http_followups_preserve_history_and_repeated_intent_does_not_reexecute(collections):
    from docweave.evaluation.execution import execute_http_turn
    c = collections
    chat = await ready_chat(c)
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    histories = []
    async def execute(turn):
        async with c['owner'].connect() as connection:
            job = await connection.scalar(text('SELECT id FROM app.personal_jobs WHERE turn_id=CAST(:turn AS uuid)'), {'turn': turn})
        async with worker.begin() as connection:
            claimed = await personal.claim_job(connection, job)
            token = UUID(claimed['lease_token'])
            histories.append(await personal.history(connection, job, token))
            await personal.finish_job(connection, job, token, {'status': 'completed', 'answer': 'Synthetic fixture response',
                'citations': [], 'expected_revision': claimed['project']['context_revision'], 'expected_policy_epoch': 1})
        return {'stages': [], 'answer': 'Synthetic fixture response'}
    try:
        options = dict(client=c['admin'], headers=c['headers'], conversation_id=chat, execute_job=execute)
        first = SimpleNamespace(id='first', query='What are the project goals?')
        result = await execute_http_turn(first, **options)
        assert result['released_turn']['status'] == 'completed'
        assert result['pipeline']['answer'] == 'Synthetic fixture response'
        assert (await execute_http_turn(first, **options))['released_turn']['id'] == result['released_turn']['id']
        assert len(histories) == 1
        followup = await execute_http_turn(SimpleNamespace(id='followup', query='Which of those goals remains open?'), **options)
        assert followup['released_turn']['status'] == 'completed'
        assert histories[0] == [] and histories[1][0]['message'] == first.query
        assert histories[1][0]['answer'] == 'Synthetic fixture response'
    finally:
        await worker.dispose()


async def test_policy_blocked_http_result_does_not_include_generated_capture(collections):
    from docweave.evaluation.execution import execute_http_turn
    c = collections
    chat = await ready_chat(c)
    async def block(turn):
        async with c['owner'].begin() as connection:
            await connection.execute(text("UPDATE app.turns SET status='blocked_policy' WHERE id=CAST(:turn AS uuid)"), {'turn': turn})
        return {'answer': 'withheld generated text', 'blocks': ['withheld block'], 'stages': []}
    result = await execute_http_turn(SimpleNamespace(id='blocked', query='Explain the project'),
        client=c['admin'], headers=c['headers'], conversation_id=chat, execute_job=block)
    assert result['http_status'] == 200 and result['released_turn']['status'] == 'blocked_policy'
    assert result['pipeline'] == {'stages': []}


async def test_execution_error_is_recorded_without_private_exception_text(collections):
    from docweave.evaluation.execution import execute_http_turn
    c = collections
    chat = await ready_chat(c)
    async def fail(turn):
        raise ValueError('sensitive exception payload')
    result = await execute_http_turn(SimpleNamespace(id='error', query='Explain the project'),
        client=c['admin'], headers=c['headers'], conversation_id=chat, execute_job=fail)
    assert result['outcome'] == 'execution_error' and result['execution_error'] == 'ValueError'
    assert result['released_turn']['status'] == 'queued'
    assert 'sensitive exception payload' not in str(result)


async def test_capture_retains_only_numeric_token_usage_in_diagnostic_metadata(monkeypatch):
    from docweave.evaluation.personal import EvaluationAnswerEngine
    from docweave.services.answer_engine import AnswerEngine
    identity = str(UUID(int=1))
    capture = {}
    engine = EvaluationAnswerEngine({'id': identity, 'actor_id': identity,
        'project': {'id': identity, 'context_revision': 1}, 'turn': {'id': identity}},
        capture=capture, engine=None, read_engine=None, config={}, generation_id=UUID(int=2), authorize=None)
    async def response(*args):
        return {'usage': {'prompt_tokens': 10, 'completion_tokens': True, 'unexpected': 'sensitive echo',
                          'completion_tokens_details': {'reasoning_tokens': 3, 'unexpected': 'sensitive detail'}}}
    monkeypatch.setattr(AnswerEngine, 'dispatch', response)
    await engine.dispatch({'model': 'fixture'}, {'id': identity, 'model': 'fixture'}, 'query_embedding', True)
    assert capture['stages'][0]['reported_usage'] == {'prompt_tokens': 10, 'reasoning_tokens': 3}
