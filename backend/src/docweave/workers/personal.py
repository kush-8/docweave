"""Personal project worker: python -m docweave.workers.personal [--once]."""
import argparse
import asyncio
import json
import os
import sys
from dotenv import dotenv_values
from uuid import UUID
import procrastinate
from docweave.core.github_settings import GitHubSettings
from docweave.core.settings import database_url,storage_root
from docweave.core.paths import ROOT
from docweave.storage.artifacts import ArtifactStore
from docweave.storage.backups import expire_backups
from docweave.services.shared_ingestion import run_catalog_job
from docweave.db.engine import make_engine
from docweave.integrations.github import GitHubClient
from docweave.repositories import personal as repository
from docweave.services.personal_worker import run_personal_job
from docweave.services.answer_engine import AnswerEngine
from docweave.services.catalog_embeddings import make_embedder
from docweave.services.private_indexing import run_private_index_job, reconcile_private_indexes
from docweave.services.guardrails import run_rescan,reconcile_rescans
from docweave.services.ingestion import reconcile_artifacts
from docweave.services.deletions import assert_reconciled
from docweave.services.retention import overdue, mark, assert_current


async def recover_jobs(queue, engine, generation_id=None, *, store=None, backup_root=None):
    stalled = await queue.job_manager.get_stalled_jobs(queue='personal')
    for job in stalled:
        if job.task_name in ('docweave.personal', 'docweave.catalog', 'docweave.private_index', 'docweave.guardrail_rescan'):
            async with engine.begin() as connection:
                await repository.retry_stalled(connection, job.id)
    async with engine.begin() as connection:
        await repository.recover_jobs(connection)
    await reconcile_rescans(engine)
    if generation_id is not None:
        await reconcile_private_indexes(engine,generation_id)
    if store is not None:
        await reconcile_artifacts(engine,store)
    if backup_root is not None:
        results = await asyncio.to_thread(expire_backups, backup_root)
        if results:
            print(json.dumps({"backup_retention": results}), flush=True)
        if any(item['status'] != 'deleted' for item in results):
            return False
    return True

async def run_worker(*,once=False):
    settings=GitHubSettings.load()
    if settings is None:
        raise ValueError('GitHub configuration is required')
    url=database_url('WORKER_DATABASE_URL')
    engine=make_engine(url)
    connector=procrastinate.PsycopgConnector(conninfo=url.set(drivername='postgresql').render_as_string(hide_password=False),kwargs={'options':'-c search_path=queue,pg_catalog'},min_size=1,max_size=2)
    queue=procrastinate.App(connector=connector)
    client=GitHubClient(settings)
    values={**dotenv_values(ROOT / ".env"),**os.environ}
    generation_id=UUID(values["RAG_GENERATION_ID"]) if values.get("RAG_GENERATION_ID") else None
    store=ArtifactStore(storage_root())
    read_engine=make_engine(database_url("DATABASE_URL"))
    def answerer_factory(job,authorize):
        return AnswerEngine(job,engine=engine,read_engine=read_engine,config=values,generation_id=generation_id,authorize=authorize)
    @queue.task(name='docweave.personal',queue='personal',retry=False)
    async def process(job_id):
        await assert_current(engine, artifact_root=store.root)
        await run_personal_job(UUID(job_id),engine=engine,settings=settings,client=client,generation_id=generation_id,answerer_factory=answerer_factory)
    @queue.task(name='docweave.catalog',queue='personal',lock='public-catalog',retry=False)
    async def catalog(job_id):
        await assert_current(engine, artifact_root=store.root)
        await run_catalog_job(UUID(job_id),engine=engine,store=store,embedder_factory=lambda job,token:make_embedder(job,token,engine=engine,config=values))
    @queue.task(name='docweave.private_index',queue='personal',retry=False)
    async def private_index(job_id):
        await assert_current(engine, artifact_root=store.root)
        await run_private_index_job(UUID(job_id),engine=engine,store=store,settings=settings,client=client,config=values)
    @queue.task(name='docweave.guardrail_rescan',queue='personal',retry=False)
    async def guardrail_rescan(job_id):
        await assert_current(engine, artifact_root=store.root)
        await run_rescan(UUID(job_id),engine=engine,store=store)
    async def reconcile():
        try:
            while True:
                healthy = await recover_jobs(queue, engine, generation_id, store=store, backup_root=ROOT / "backups")
                if not healthy or not await overdue(engine):
                    await asyncio.to_thread(mark, engine, healthy, artifact_root=store.root)
                    return healthy
                await asyncio.sleep(0.05)
        except Exception:
            await asyncio.to_thread(mark, engine, False, artifact_root=store.root)
            raise
    try:
        await assert_reconciled(engine, artifact_root=store.root)
        async with queue.open_async():
            while not await reconcile():
                if once:
                    return
                await asyncio.sleep(10)
            async def maintain():
                while True:
                    await asyncio.sleep(10)
                    await assert_reconciled(engine, artifact_root=store.root)
                    if not await reconcile():
                        raise ValueError('Retention cleanup failed; restart after repairing the reported backup')
            async with asyncio.TaskGroup() as tasks:
                maintenance = tasks.create_task(maintain())
                await queue.run_worker_async(queues=['personal'],wait=not once,concurrency=1,
                    install_signal_handlers=False,update_heartbeat_interval=10,stalled_worker_timeout=30,
                    shutdown_graceful_timeout=0)
                maintenance.cancel()
    finally:
        await engine.dispose()
        await read_engine.dispose()

def main():
    parser=argparse.ArgumentParser(description='Run durable personal project jobs')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    asyncio.run(run_worker(once=args.once),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)

if __name__=='__main__':
    main()
