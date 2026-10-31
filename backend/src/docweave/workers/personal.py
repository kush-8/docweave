"""Personal project worker: python -m docweave.workers.personal [--once]."""
import argparse
import asyncio
import os
from dotenv import dotenv_values
from uuid import UUID
import procrastinate
from docweave.core.github_settings import GitHubSettings
from docweave.core.settings import database_url,storage_root
from docweave.core.paths import ROOT
from docweave.storage.artifacts import ArtifactStore
from docweave.services.shared_ingestion import run_catalog_job
from docweave.db.engine import make_engine
from docweave.integrations.github import GitHubClient
from docweave.repositories import personal as repository
from docweave.services.personal_worker import run_personal_job
from docweave.services.answer_engine import AnswerEngine
from docweave.services.catalog_embeddings import make_embedder

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
        await run_personal_job(UUID(job_id),engine=engine,settings=settings,client=client,generation_id=generation_id,answerer_factory=answerer_factory)
    @queue.task(name='docweave.catalog',queue='personal',lock='public-catalog',retry=False)
    async def catalog(job_id):
        await run_catalog_job(UUID(job_id),engine=engine,store=store,embedder_factory=lambda job,token:make_embedder(job,token,engine=engine,config=values))
    try:
        async with queue.open_async():
            # Durable recovery also covers missed source-completion notifications.
            async with engine.connect() as connection:
                pending=await repository.pending_jobs(connection)
            for job in pending:
                await process.configure(lock='personal:'+str(job['project_id'])).defer_async(job_id=str(job['id']))
            await queue.run_worker_async(queues=['personal'],wait=not once,concurrency=1)
    finally:
        await engine.dispose()
        await read_engine.dispose()

def main():
    parser=argparse.ArgumentParser(description='Run durable personal project jobs')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    asyncio.run(run_worker(once=args.once))

if __name__=='__main__':
    main()
