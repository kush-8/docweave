import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from uuid import uuid4
from tests.database.test_database import A,PA,databases,test_urls
from tests.legacy.test_budget import profile
from docweave.core.settings import database_url
from docweave.db.engine import make_engine

pytestmark=pytest.mark.anyio

async def test_global_personal_admission_needs_consent_and_never_replays(databases):
    owner,_=databases
    identity=await profile(owner)
    worker=make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    async with owner.begin() as c:
        await c.execute(text('UPDATE app.projects SET owner_user_id=:a WHERE id=:p'),{'a':A,'p':PA})
    values={'p':PA,'a':A,'profile':identity,'op':'a'*64,'body':'b'*64}
    statement=text('SELECT app.personal_provider_claim(:p,:a,:profile,:op,:body,1,1)')
    try:
        with pytest.raises(DBAPIError):
            async with worker.begin() as c:
                await c.execute(statement,values)
        async with owner.begin() as c:
            for processor in ('test:budget:google','test:budget:groq'):
                await c.execute(text('INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,:processor,:a)'),{'p':PA,'processor':processor,'a':A})
        async with worker.begin() as c:
            result=await c.scalar(statement,values)
            assert __import__('decimal').Decimal(result['maximum_usd'])==__import__('decimal').Decimal('0.6')
        with pytest.raises(DBAPIError):
            async with worker.begin() as c:
                await c.execute(statement,values)
        async with owner.connect() as c:
            assert await c.scalar(text("SELECT status FROM app.cost_reservations WHERE operation_hash=:op"),values)=='uncertain'
            assert await c.scalar(text('SELECT workspace_id FROM app.cost_reservations WHERE operation_hash=:op'),values) is None
    finally:
        await worker.dispose()
