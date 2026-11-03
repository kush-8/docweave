import asyncio
from uuid import UUID
from sqlalchemy import text
from docweave.core.settings import deletion_root
from docweave.storage.deletions import DeletionJournal


async def record_deletion(connection, kind, identity, project_id, artifacts=(), *, journal=None):
    journal = journal or DeletionJournal(deletion_root())
    artifacts = sorted(set(str(item) for item in artifacts))
    for start in range(0, max(1, len(artifacts)), 512):
        key = await asyncio.to_thread(journal.record, kind, identity, project_id, artifacts[start:start + 512])
        await connection.execute(text('INSERT INTO app.deletion_receipts(hash) VALUES(:hash) ON CONFLICT DO NOTHING'), {'hash': key})


async def receipt_hashes(connection):
    return set((await connection.execute(text('SELECT hash FROM app.deletion_receipts'))).scalars())


async def replay_records(connection, entries, journal):
    if await connection.scalar(text('SELECT current_user')) != 'docweave_migrator':
        raise ValueError('Deletion replay requires the operator role')
    if (await connection.scalar(text('SELECT count(*) FROM app.provider_profiles WHERE enabled'))
        or await connection.scalar(text("SELECT count(*) FROM queue.procrastinate_jobs WHERE status='doing'"))):
        raise ValueError('Disable provider profiles and drain workers before restoring')
    receipts = set((await connection.execute(text('SELECT hash FROM app.deletion_receipts'))).scalars())
    if not receipts.issubset(entries):
        raise ValueError('Latest journal is incomplete; recover it before replay')
    targets = []
    seen = set()
    for key, entry in entries.items():
        target = (entry['kind'], entry['id'], entry['project_id'])
        if target in seen:
            continue
        seen.add(target)
        if entry['kind'] == 'conversation':
            query = 'SELECT c.project_id,p.owner_user_id actor,p.workspace_id FROM app.conversations c JOIN app.projects p ON p.id=c.project_id WHERE c.id=:id FOR UPDATE OF c'
        else:
            table = 'documents' if entry['kind'] == 'document' else 'sources'
            query = f'SELECT c.project_id,p.owner_user_id actor,p.workspace_id FROM app.{table} d JOIN app.collections c ON c.id=d.collection_id JOIN app.projects p ON p.id=c.project_id WHERE d.id=:id FOR UPDATE OF d'
        row = (await connection.execute(text(query), {'id': UUID(entry['id'])})).mappings().first()
        if row is not None and (str(row['project_id']) != entry['project_id'] or row['actor'] is None):
            raise ValueError('Restored target requires verified project/ownership reconciliation')
        targets.append((key, entry, row))
    # An interrupted original write may contain only the first batch; seal every artifact known to this restored target.
    for _, entry, row in targets:
        if row is not None and entry['kind'] != 'conversation':
            predicate = 'd.id=:id' if entry['kind'] == 'document' else 'd.source_id=:id'
            artifacts = list((await connection.execute(text(f'''SELECT v.id FROM app.document_versions v
                JOIN app.documents d ON d.id=v.document_id WHERE {predicate}
                UNION SELECT j.id FROM app.ingestion_jobs j JOIN app.documents d ON d.id=j.document_id WHERE {predicate}'''),
                {'id': UUID(entry['id'])})).scalars())
            await record_deletion(connection, entry['kind'], entry['id'], entry['project_id'], artifacts, journal=journal)
    for key, entry, row in targets:
        identity = UUID(entry['id'])
        if row is not None:
            await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true),set_config('docweave.workspace_id',:workspace,true)"),
                {'actor': str(row['actor']), 'workspace': str(row['workspace_id']) if row['workspace_id'] else ''})
            if entry['kind'] == 'conversation':
                if not await connection.scalar(text('SELECT app.personal_delete_conversation(:id)'), {'id': identity}):
                    raise ValueError('Restored conversation could not be fenced')
            else:
                documents = [identity] if entry['kind'] == 'document' else list((await connection.execute(
                    text('SELECT id FROM app.documents WHERE source_id=:id ORDER BY id'), {'id': identity})).scalars())
                for document in documents:
                    if await connection.scalar(text('SELECT deleted_at IS NULL FROM app.documents WHERE id=:id'), {'id': document}):
                        await connection.scalar(text('SELECT app.delete_ingestion_document(:id)'), {'id': document})
                    await connection.scalar(text('SELECT app.personal_cleanup_deleted_documents(:id)'), {'id': document})
                    await connection.execute(text('DELETE FROM app.chunks WHERE document_id=:id'), {'id': document})
                if entry['kind'] == 'source':
                    await connection.execute(text('UPDATE app.sources SET deleted_at=coalesce(deleted_at,clock_timestamp()) WHERE id=:id'), {'id': identity})
    for key in entries:
        await connection.execute(text('INSERT INTO app.deletion_receipts(hash) VALUES(:hash) ON CONFLICT DO NOTHING'), {'hash': key})
