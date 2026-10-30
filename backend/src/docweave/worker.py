"""Separate ingestion process: python -m docweave.worker [--once]."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from uuid import UUID

import procrastinate
from sqlalchemy import text

from docweave.db import make_engine
from docweave.ingestion import ArtifactStore, container_parse, reconcile_artifacts, run_ingestion, storage_root
from docweave.settings import database_url


async def recover_jobs(queue, engine):
    stalled = await queue.job_manager.get_stalled_jobs(queue="ingestion", task_name="docweave.ingest")
    for job in stalled:
        async with engine.connect() as connection:
            recoverable = await connection.scalar(text("SELECT app.ingestion_recoverable(:id)"), {"id": UUID(job.task_kwargs["job_id"])})
        if recoverable:
            await queue.job_manager.retry_job_by_id_async(job.id, retry_at=datetime.now(timezone.utc))


async def run_worker(url, store, *, wait=True, parser=container_parse):
    engine = make_engine(url)
    connector = procrastinate.PsycopgConnector(conninfo=url.set(drivername="postgresql").render_as_string(hide_password=False),
        kwargs={"options": "-c search_path=queue,pg_catalog"}, min_size=1, max_size=3)
    queue = procrastinate.App(connector=connector)

    @queue.task(name="docweave.ingest", queue="ingestion", lock="ingestion",
        retry=procrastinate.RetryStrategy(max_attempts=3, wait=1, retry_exceptions=(OSError, TimeoutError)))
    async def ingest(job_id):
        await run_ingestion(UUID(job_id), engine=engine, store=store, parser=parser)

    async def maintain():
        while True:
            await asyncio.sleep(10)
            await recover_jobs(queue, engine)
            await reconcile_artifacts(engine, store)

    try:
        async with queue.open_async():
            await recover_jobs(queue, engine)
            await reconcile_artifacts(engine, store)
            async with asyncio.TaskGroup() as tasks:
                maintenance = tasks.create_task(maintain())
                await queue.run_worker_async(queues=["ingestion"], concurrency=1, wait=wait, install_signal_handlers=False,
                    update_heartbeat_interval=10, stalled_worker_timeout=30)
                maintenance.cancel()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--once", action="store_true", help="Drain currently available ingestion jobs and exit.")
    args = arguments.parse_args()
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(run_worker(database_url("WORKER_DATABASE_URL"), ArtifactStore(storage_root()), wait=not args.once), loop_factory=loop_factory)
