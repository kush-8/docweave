import pytest
from sqlalchemy import text

from tests.database.test_database import A, PA, WA, databases, test_urls, migrate  # noqa: F401

pytestmark = pytest.mark.anyio

RETIRED = (
    'app.create_invitation(text,text,text)', 'app.list_invitations(timestamptz,uuid,integer)',
    'app.revoke_invitation(uuid)', 'app.accept_invitation(text)',
    'app.create_project(jsonb)', 'app.update_project(uuid,integer,jsonb)',
    'app.replace_project_documentation(uuid)',
)


async def test_retired_schema_is_absent_and_retained_operator_functions_remain(databases):
    owner, _ = databases
    from docweave.db.models import Base
    async with owner.connect() as c:
        for name in ('invitations', 'documentation_requests'):
            assert await c.scalar(text('SELECT to_regclass(:name)'), {'name': 'app.'+name}) is None
            assert 'app.'+name not in Base.metadata.tables
        for signature in RETIRED:
            assert await c.scalar(text('SELECT to_regprocedure(:signature)'), {'signature': signature}) is None
        for signature in ('app.collection_can(uuid,text)', 'app.collection_workspace(uuid)'):
            assert await c.scalar(text('SELECT to_regprocedure(:signature)'), {'signature': signature}) is not None


@pytest.mark.parametrize('table', ['invitations', 'documentation_requests'])
async def test_retirement_refuses_existing_records_without_erasing_them(databases, test_urls, table):
    owner, _ = databases
    await migrate(test_urls[1], '0042_deletion_receipts', downgrade=True)
    try:
        async with owner.begin() as c:
            if table == 'invitations':
                await c.execute(text("""INSERT INTO app.invitations(workspace_id,created_by,email,role,token_hash,expires_at)
                    VALUES(:workspace,:actor,'synthetic@example.test','member',:hash,now()+interval '1 day')"""),
                    {'workspace': WA, 'actor': A, 'hash': 'a'*64})
            else:
                await c.execute(text("""INSERT INTO app.documentation_requests(workspace_id,project_id,requested_by,context_revision,state,reason)
                    VALUES(:workspace,:project,:actor,1,'pending_review','version_unresolved')"""),
                    {'workspace': WA, 'project': PA, 'actor': A})
        with pytest.raises(ValueError, match='preserv'):
            await migrate(test_urls[1], 'head')
        async with owner.connect() as c:
            assert await c.scalar(text('SELECT count(*) FROM app.'+table)) == 1
            assert await c.scalar(text('SELECT version_num FROM app.alembic_version')) == '0042_deletion_receipts'
    finally:
        async with owner.begin() as c:
            await c.execute(text('DELETE FROM app.'+table))
        await migrate(test_urls[1], 'head')


@pytest.mark.parametrize('kind,sql', [
    ('FUNCTION', 'CREATE FUNCTION app.retirement_consumer() RETURNS bigint LANGUAGE sql AS $$ SELECT count(*) FROM app.invitations $$'),
    ('PROCEDURE', 'CREATE PROCEDURE app.retirement_consumer() LANGUAGE plpgsql AS $$ BEGIN PERFORM count(*) FROM app.invitations; END $$'),
    ('FUNCTION', 'CREATE FUNCTION app.retirement_consumer() RETURNS bigint LANGUAGE plpgsql SET search_path=app AS $$ BEGIN RETURN (SELECT count(*) FROM invitations); END $$'),
])
async def test_unknown_sql_consumer_blocks_retirement(databases, test_urls, kind, sql):
    owner, _ = databases
    await migrate(test_urls[1], '0042_deletion_receipts', downgrade=True)
    try:
        async with owner.begin() as c:
            await c.execute(text(sql))
        with pytest.raises(ValueError, match='consumer'):
            await migrate(test_urls[1], 'head')
        async with owner.connect() as c:
            assert await c.scalar(text("SELECT to_regclass('app.invitations')")) is not None
    finally:
        async with owner.begin() as c:
            await c.execute(text('DROP '+kind+' app.retirement_consumer()'))
        await migrate(test_urls[1], 'head')


async def test_empty_retirement_roundtrip_restores_original_functions_and_grants(databases, test_urls):
    owner, _ = databases
    async def definitions():
        async with owner.connect() as c:
            return [(await c.execute(text("SELECT pg_get_functiondef(CAST(:name AS regprocedure)),proacl::text FROM pg_proc WHERE oid=CAST(:name AS regprocedure)"), {'name': signature})).one()
                for signature in (*RETIRED, 'app.change_member(uuid,text)')]
    await migrate(test_urls[1], '0042_deletion_receipts', downgrade=True)
    before = await definitions()
    await migrate(test_urls[1], 'head')
    await migrate(test_urls[1], '0042_deletion_receipts', downgrade=True)
    assert await definitions() == before
    await migrate(test_urls[1], 'head')
