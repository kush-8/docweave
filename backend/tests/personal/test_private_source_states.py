import pytest
from sqlalchemy import text
from tests.personal.test_private_indexing import private_index
from tests.support.personal import collections
from tests.github.test_github import github_login
from tests.database.test_database import databases,test_urls

pytestmark=pytest.mark.anyio


async def test_private_index_progress_and_admission_are_truthful(private_index):
    c=private_index
    c['data']['app'].state.runtime_config['RAG_GENERATION_ID']=str(c['generation'])
    path=f"/api/v1/projects/{c['project']}/documentation"
    async def current():
        response=await c['admin'].get(path)
        assert response.status_code==200,response.text
        return response.json()['items'][0]
    item=await current()
    assert item['status']=='waiting_for_sources' and item['entry']['active_job']
    async with c['owner'].begin() as connection:
        await connection.execute(text("UPDATE app.private_index_jobs SET status='capacity' WHERE id=:id"),{'id':c['job']})
    assert (await current())['status']=='capacity'
    async with c['owner'].begin() as connection:
        await connection.execute(text("UPDATE app.private_index_jobs SET status='queued' WHERE id=:id"),{'id':c['job']})
        await connection.execute(text('DELETE FROM app.project_processor_approvals WHERE project_id=CAST(:id AS uuid)'),{'id':c['project']})
    item=await current()
    assert item['status']=='consent_required' and not item['entry']['active_job']
    c['data']['app'].state.runtime_config.pop('RAG_GENERATION_ID')
    item=await current()
    assert item['status']=='capacity' and not item['entry']['active_job']


async def test_stale_private_queue_delivery_is_retried_once(private_index):
    from docweave.services.private_indexing import reconcile_private_indexes
    from docweave.repositories import personal
    c=private_index
    assert await reconcile_private_indexes(c['worker'],c['generation'])==1
    async with c['owner'].begin() as connection:
        await connection.execute(text('SET LOCAL search_path=queue,pg_catalog'))
        queue_id=await connection.scalar(text("UPDATE queue.procrastinate_jobs SET status='doing',worker_id=NULL WHERE task_name='docweave.private_index' RETURNING id"))
    async with c['worker'].begin() as connection:
        assert await personal.retry_stalled(connection,queue_id) is True
        assert await personal.retry_stalled(connection,queue_id) is False
