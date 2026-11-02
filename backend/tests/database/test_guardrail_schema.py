import pytest
from sqlalchemy import text
from tests.database.test_database import databases,test_urls,migrate

pytestmark=pytest.mark.anyio


async def test_empty_guardrail_migration_roundtrip_and_model_parity(databases,test_urls):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from docweave.db.models import Base
    owner,_=databases
    await migrate(test_urls[1],'0039_conversation_summaries',downgrade=True)
    await migrate(test_urls[1],'head')
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT has_function_privilege('docweave_worker','app.activate_guardrail_policy(text,bigint)','EXECUTE')")) is False
        def check(sync):
            context=MigrationContext.configure(sync,opts={'include_schemas':True,'version_table_schema':'app','include_name':lambda name,type_,parent: name=='app' if type_=='schema' else True})
            return compare_metadata(context,Base.metadata)
        assert await connection.run_sync(check)==[]
