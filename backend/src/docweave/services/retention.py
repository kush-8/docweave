import asyncio
import hashlib
import json
import math
from pathlib import Path
import time
from docweave.core.settings import deletion_root, storage_root
from docweave.evaluation.reports import write_report
from docweave.repositories import retention as repository
from docweave.storage.deletions import DeletionJournal


def health_path(engine, artifact_root=None):
    root = deletion_root()
    DeletionJournal(root).check_root()
    storage = Path(artifact_root if artifact_root is not None else storage_root()).resolve()
    target = (engine.url.host, engine.url.port, engine.url.database, str(root), str(storage))
    key = hashlib.sha256(json.dumps(target).encode()).hexdigest()
    path = root.parent / ('.retention-'+key+'.json')
    if path.is_symlink() or path.is_junction():
        raise ValueError('Retention health cannot be a link')
    return path


def mark(engine, healthy, *, artifact_root=None):
    if type(healthy) is not bool:
        raise ValueError('Retention outcome must be explicit')
    write_report(health_path(engine, artifact_root), {'format': 'retention-health-v1', 'ok': healthy,
        'completed': time.monotonic() if healthy else None})


async def overdue(engine):
    async with engine.connect() as connection:
        return await repository.overdue(connection)


async def assert_current(engine, *, artifact_root=None, since=None):
    if await overdue(engine):
        raise ValueError('Overdue retention cleanup must finish before private traffic')
    path = health_path(engine, artifact_root)
    with path.open('rb') as file:
        data = file.read(4097)
    if len(data) > 4096:
        raise ValueError('Oversized retention health record')
    state = json.loads(data)
    if (set(state) != {'format', 'ok', 'completed'} or state['format'] != 'retention-health-v1'
        or state['ok'] is not True or type(state['completed']) not in (int, float)
        or not math.isfinite(state['completed']) or not 0 <= time.monotonic()-state['completed'] <= 30
        or since is not None and state['completed'] < since):
        raise ValueError('Successful current retention maintenance is required')


async def wait_current(engine):
    # shortcut: shared monotonic clocks/files assume one host; use database-backed health for distributed workers.
    since = time.monotonic()
    while True:
        try:
            await assert_current(engine, since=since)
            return
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            if time.monotonic()-since >= 30:
                raise ValueError('Current worker cleanup did not complete after API startup') from None
            await asyncio.sleep(0.1)
