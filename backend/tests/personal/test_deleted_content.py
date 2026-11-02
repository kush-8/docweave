"""Deleted chat content is erased without losing financial/replay identity."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.database.test_database import A, B, PA, PB, WA, databases, test_urls, migrate  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.db.sessions import domain_session
from docweave.repositories import personal

pytestmark = pytest.mark.anyio


async def test_cleanup_migration_roundtrip(databases, test_urls):
    await migrate(test_urls[1], '0040_guardrail_lifecycle', downgrade=True)
    await migrate(test_urls[1], 'head')


async def test_chat_deletion_erases_content_and_preserves_other_owners_and_ids(databases):
    owner, runtime = databases
    chats, turns = [uuid4(), uuid4()], [uuid4(), uuid4()]
    async with owner.begin() as connection:
        for actor, project, chat, turn in zip((A, B), (PA, PB), chats, turns):
            await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:project'),
                {'actor': actor, 'project': project})
            await connection.execute(text("""INSERT INTO app.conversations(id,project_id,status,progress,summary)
                VALUES(:id,:project,'ready','private progress','{"text":"private summary"}')"""), {'id': chat, 'project': project})
            await connection.execute(text("""INSERT INTO app.turns(id,conversation_id,sequence,idempotency_key,message,
                answer,citations,required_dependencies,progress,status) VALUES(:id,:chat,1,:key,'private question',
                'private answer','[{"quote":"private quote"}]','["private dependency"]','private progress','completed')"""),
                {'id': turn, 'chat': chat, 'key': uuid4()})
    async with domain_session(runtime, B) as connection:
        assert await personal.delete_conversation(connection, chats[0]) is False
    async with domain_session(runtime, A) as connection:
        assert await personal.delete_conversation(connection, chats[0]) is True
        assert await personal.delete_conversation(connection, chats[0]) is True
        assert await personal.conversation(connection, chats[0]) is None
        assert await personal.turn(connection, turns[0]) is None
    async with owner.connect() as connection:
        row = (await connection.execute(text('SELECT message,answer,citations,required_dependencies,progress FROM app.turns WHERE id=:id'),
            {'id': turns[0]})).one()
        assert tuple(row) == ('', None, [], [], None)
        assert (await connection.execute(text('SELECT summary,progress FROM app.conversations WHERE id=:id'), {'id': chats[0]})).one() == (None, None)
        assert await connection.scalar(text('SELECT message FROM app.turns WHERE id=:id'), {'id': turns[1]}) == 'private question'
        assert await connection.scalar(text('SELECT count(*) FROM app.turns')) == 2
        assert await connection.scalar(text('SELECT count(*) FROM app.conversations')) == 2


async def test_worker_cleanup_drains_old_tombstones_in_batches_and_preserves_finances(databases, test_urls):
    from tests.providers.test_budget import profile
    owner, runtime = databases
    identity = await profile(owner)
    async with owner.begin() as connection:
        await connection.execute(text("""INSERT INTO app.cost_reservations(workspace_id,actor_id,project_id,profile_id,
            operation_hash,month,input_tokens,output_tokens,maximum_usd,status) VALUES(:workspace,:actor,:project,
            :profile,:hash,date_trunc('month',now()),1,1,0.123456789012,'uncertain')"""),
            {'workspace': WA, 'actor': A, 'project': PA, 'profile': identity, 'hash': 'a' * 64})
        before = list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r'))).scalars())
        await connection.execute(text("""WITH chats AS (
            INSERT INTO app.conversations(project_id,status,deleted_at) SELECT :project,'deleted',now()
            FROM generate_series(1,101) RETURNING id
            ) INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message,status)
            SELECT id,1,gen_random_uuid(),'old deleted question','completed' FROM chats"""), {'project': PA})
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_runtime','app.personal_cleanup_deleted_conversations(uuid)','EXECUTE')")) is False
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_worker','app.personal_cleanup_deleted_conversations(uuid)','EXECUTE')")) is True
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        for remaining in (1, 0, 0):
            async with worker.begin() as connection:
                await personal.recover_jobs(connection)
            async with owner.connect() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM app.turns WHERE message<>''")) == remaining
                assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r'))).scalars()) == before
        await migrate(test_urls[1], '0040_guardrail_lifecycle', downgrade=True)
        await migrate(test_urls[1], 'head')
        async with owner.connect() as connection:
            assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r'))).scalars()) == before
            assert await connection.scalar(text('SELECT count(*) FROM app.turns')) == 101
    finally:
        await worker.dispose()


async def test_worker_expires_auth_secrets_without_waiting_for_a_login(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        for prefix, expiry in (('a', "now()-interval '1 second'"), ('b', "now()+interval '1 hour'")):
            await connection.execute(text(f"""INSERT INTO app.auth_flows(state_hash,browser_hash,encrypted_data,expires_at)
                VALUES(:hash,:hash,'encrypted flow',{expiry})"""), {'hash': prefix * 64})
            await connection.execute(text(f"""INSERT INTO app.auth_sessions(token_hash,user_id,encrypted_token,expires_at)
                VALUES(:hash,:actor,'encrypted token',{expiry})"""), {'hash': prefix * 64, 'actor': A})
            await connection.execute(text(f"""INSERT INTO app.auth_rate_limits(bucket,attempts,resets_at)
                VALUES(:hash,1,{expiry})"""), {'hash': prefix * 64})
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        async with worker.begin() as connection:
            await personal.recover_jobs(connection)
        async with owner.connect() as connection:
            for table, column in (('auth_flows', 'state_hash'), ('auth_sessions', 'token_hash'), ('auth_rate_limits', 'bucket')):
                assert list((await connection.execute(text(f'SELECT {column} FROM app.{table}'))).scalars()) == ['b' * 64]
    finally:
        await worker.dispose()
