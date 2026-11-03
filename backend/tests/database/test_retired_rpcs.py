import pytest
from sqlalchemy import text
from tests.database.test_database import databases, test_urls, migrate  # noqa: F401

pytestmark = pytest.mark.anyio

RETIRED = (
    'app.create_workspace(text)', 'app.list_workspaces(timestamptz,uuid,integer)',
    'app.list_members(timestamptz,uuid,integer)', 'app.change_member(uuid,text)',
    'app.project_workspace(uuid)', 'app.project_view(uuid)', 'app.create_collection(uuid,text)',
    'app.replace_collection_grants(uuid,integer,jsonb)', 'app.replace_processing_policy(text,uuid,integer,jsonb)',
    'app.collection_grants(uuid)', 'app.processing_policy(text,uuid)', 'app.lock_workspace_owner()',
    'app.personal_assessment_view(uuid)',
)


async def test_unused_product_rpcs_absent_but_active_policy_helpers_remain(databases):
    owner, _ = databases
    async with owner.connect() as c:
        for signature in RETIRED:
            assert await c.scalar(text('SELECT to_regprocedure(:name)'), {'name': signature}) is None
        for signature in ('app.collection_can(uuid,text)', 'app.collection_workspace(uuid)',
            'app.reconcile_member_grants()', 'app.immutable_processor()', 'app.personal_processing_policy(uuid)',
            'app.personal_version_assessment_view(uuid,uuid)'):
            assert await c.scalar(text('SELECT to_regprocedure(:name)'), {'name': signature}) is not None


@pytest.mark.parametrize('kind,sql', [
    ('FUNCTION', 'CREATE FUNCTION app.retired_rpc_consumer() RETURNS jsonb LANGUAGE sql AS $$ SELECT app.collection_grants(NULL::uuid) $$'),
    ('PROCEDURE', "CREATE PROCEDURE app.retired_rpc_consumer() LANGUAGE plpgsql SET search_path=app AS $$ BEGIN PERFORM create_workspace('Synthetic'); END $$"),
])
async def test_unknown_routine_call_blocks_rpc_retirement(databases, test_urls, kind, sql):
    owner, _ = databases
    await migrate(test_urls[1], '0043_retire_manual_schema', downgrade=True)
    try:
        async with owner.begin() as c:
            await c.execute(text(sql))
        with pytest.raises(ValueError, match='consumer'):
            await migrate(test_urls[1], 'head')
        async with owner.connect() as c:
            assert await c.scalar(text("SELECT to_regprocedure('app.create_workspace(text)')")) is not None
    finally:
        async with owner.begin() as c:
            await c.execute(text('DROP '+kind+' app.retired_rpc_consumer()'))
        await migrate(test_urls[1], 'head')


async def test_rpc_downgrade_restores_exact_0043_bodies_and_grants(databases, test_urls):
    owner, _ = databases
    async def definitions():
        async with owner.connect() as c:
            return [(await c.execute(text('SELECT pg_get_functiondef(oid),proacl::text FROM pg_proc WHERE oid=CAST(:name AS regprocedure)'), {'name': name})).one() for name in RETIRED]
    await migrate(test_urls[1], '0043_retire_manual_schema', downgrade=True)
    before = await definitions()
    await migrate(test_urls[1], 'head')
    await migrate(test_urls[1], '0043_retire_manual_schema', downgrade=True)
    assert await definitions() == before
    await migrate(test_urls[1], 'head')
