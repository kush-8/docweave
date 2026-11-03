"""Fail closed on unmatched external erasure intents; replay only in a drained restore."""
import asyncio
from pathlib import Path
from docweave.repositories import deletions as repository
from docweave.core.settings import deletion_root, storage_root
from docweave.storage.deletions import DeletionJournal


async def assert_reconciled(engine, *, journal=None, artifact_root=None):
    journal = journal or DeletionJournal(deletion_root())
    entries = await asyncio.to_thread(journal.entries)
    async with engine.connect() as connection:
        receipts = await repository.receipt_hashes(connection)
    if receipts != set(entries):
        raise ValueError('Latest deletion journal and database must be reconciled before release')
    root = Path(artifact_root if artifact_root is not None else storage_root())
    for entry in entries.values():
        if any((root / identity).exists() for identity in entry['artifacts']):
            raise ValueError('Deleted artifacts remain; replay erasure before release')


async def replay_deletions(*, engine, journal, store):
    entries = await asyncio.to_thread(journal.entries)
    async with engine.begin() as connection:
        await repository.replay_records(connection, entries, journal)
    # Receipts commit with database fencing; remaining artifact failures keep the release gate closed and are retriable.
    entries = await asyncio.to_thread(journal.entries)
    for entry in entries.values():
        for identity in entry['artifacts']:
            await asyncio.to_thread(store.remove, identity)
    await assert_reconciled(engine, journal=journal, artifact_root=store.root)
    return {'intents': len(entries), 'reconciled': True}
