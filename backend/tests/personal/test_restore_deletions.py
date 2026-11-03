import asyncio
import subprocess
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.support.personal import collections, github_login  # noqa: F401
from tests.database.test_database import databases, test_urls  # noqa: F401
from tests.rag.test_ingestion import ingestion, upload, work  # noqa: F401
from tests.paths import REPO_ROOT

pytestmark = pytest.mark.anyio


async def backup(c, urls):
    from docweave.repositories.ownership import preservation_snapshot
    from tests.database.test_database import checked_test_urls
    checked_test_urls(*(url.render_as_string(hide_password=False) for url in urls))
    async with c['owner'].begin() as connection:
        baseline = await preservation_snapshot(connection)
    dump = await asyncio.to_thread(subprocess.run,
        ['docker','compose','exec','-T','test-db','pg_dump','-Fc','-U','docweave_admin','docweave_test'],
        cwd=REPO_ROOT, capture_output=True, timeout=30)
    assert dump.returncode == 0, 'Disposable pre-deletion backup failed; output withheld'
    return dump.stdout, baseline


async def restore(c, dump, baseline):
    from docweave.repositories.ownership import preservation_snapshot
    for name in ('owner', 'runtime', 'worker'):
        if name in c:
            await c[name].dispose()
    restored = await asyncio.to_thread(subprocess.run,
        ['docker','compose','exec','-T','test-db','pg_restore','--clean','--if-exists','--exit-on-error',
            '-U','docweave_admin','-d','docweave_test'],
        cwd=REPO_ROOT, input=dump, capture_output=True, timeout=30)
    assert restored.returncode == 0, 'Disposable restore failed; output withheld'
    async with c['owner'].begin() as connection:
        assert await preservation_snapshot(connection) == baseline


async def seed_chat(c):
    from docweave.services.deletions import assert_reconciled
    await assert_reconciled(c['runtime'])
    c['data']['app'].state.runtime_config.pop('ANSWER_PROFILE_ID', None)
    response = await c["admin"].post(f'/api/v1/projects/{c["project"]}/conversations',
        json={}, headers=c["headers"])
    assert response.status_code == 202, response.text
    chat = response.json()["id"]
    turn = uuid4()
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.conversations SET status='ready' WHERE id=:id"), {"id": UUID(chat)})
        await connection.execute(text("""INSERT INTO app.turns(id,conversation_id,sequence,idempotency_key,message,answer,status)
            VALUES(:id,:chat,1,:key,'Synthetic private question','Synthetic private answer','completed')"""),
            {"id": turn, "chat": UUID(chat), "key": uuid4()})
    return chat, turn


async def test_restore_gate_and_replay_preserve_ids_and_financial_identity(collections, tmp_path, test_urls):
    from docweave.core.settings import deletion_root
    from docweave.storage.artifacts import ArtifactStore
    from docweave.storage.deletions import DeletionJournal
    from docweave.services.deletions import replay_deletions
    c = collections
    chat, turn = await seed_chat(c)
    from tests.providers.test_budget import profile
    selected = await profile(c['owner'], enabled=False)
    async with c['owner'].begin() as connection:
        await connection.execute(text("""INSERT INTO app.cost_reservations(actor_id,project_id,profile_id,
            operation_hash,month,input_tokens,output_tokens,maximum_usd,status)
            VALUES(:actor,:project,:profile,:hash,date_trunc('month',now()),1,1,0.123456789012,'uncertain')"""),
            {'actor': UUID(c['user']['id']), 'project': UUID(c['project']), 'profile': selected, 'hash': 'c'*64})
    dump, baseline = await backup(c, test_urls)
    assert (await c["admin"].delete(f'/api/v1/conversations/{chat}', headers=c["headers"])).status_code == 204
    journal = DeletionJournal(deletion_root())
    entries = journal.entries()
    assert len(entries) == 1
    key, entry = next(iter(entries.items()))
    assert entry["id"] == chat and entry["project_id"] == c["project"]
    async with c["owner"].begin() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.deletion_receipts WHERE hash=:key'), {"key": key}) == 1
        finances = list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r'))).scalars())
    # Restore the actual old database, retaining the newer external deletion journal.
    await restore(c, dump, baseline)
    assert (await c["admin"].get(f'/api/v1/conversations/{chat}')).status_code == 503
    store = ArtifactStore(tmp_path / "restored-artifacts")
    await replay_deletions(engine=c["owner"], journal=journal, store=store)
    await replay_deletions(engine=c["owner"], journal=journal, store=store)
    assert (await c["admin"].get(f'/api/v1/conversations/{chat}')).status_code == 404
    async with c["owner"].connect() as connection:
        assert (await connection.execute(text('SELECT message,answer FROM app.turns WHERE id=:id'), {"id": turn})).one() == ('', None)
        assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r'))).scalars()) == finances


@pytest.mark.parametrize('kind', ['document', 'source'])
async def test_document_and_source_replay_remove_restored_artifacts_and_fence_jobs(ingestion, kind, test_urls):
    from docweave.core.settings import deletion_root
    from docweave.storage.deletions import DeletionJournal
    from docweave.services.deletions import replay_deletions
    from tests.rag.test_sources import approved_selection, import_source
    c = ingestion
    if kind == 'source':
        selection = await approved_selection(c)
        response = await import_source(c, selection)
        async def fetcher(stored):
            return b'# Synthetic official\n\nUse a session dependency.\n', 'text/markdown'
        assert response.status_code == 202, response.text
        accepted = response.json()
        await work(c, accepted['job_id'], fetcher=fetcher)
        sources = (await c['admin'].get(f'/api/v1/projects/{c["project"]}/sources')).json()['items']
        target = sources[0]['id']
        async with c['owner'].connect() as connection:
            accepted['document_id'] = str(await connection.scalar(text('SELECT id FROM app.documents WHERE source_id=:id'), {'id': UUID(target)}))
    else:
        response = await upload(c)
        assert response.status_code == 202, response.text
        accepted = response.json()
        await work(c, accepted['job_id'])
        target = accepted['document_id']
    document = UUID(accepted['document_id'])
    files = {path.name: path.read_bytes() for path in c['store'].root.iterdir()}
    assert files
    dump, baseline = await backup(c, test_urls)
    path = f'/api/v1/{"documents" if kind == "document" else "sources"}/{target}'
    response = await c['admin'].delete(path, headers=c['headers'])
    assert response.status_code == 202, response.text
    journal = DeletionJournal(deletion_root())
    assert next(iter(journal.entries().values()))['kind'] == kind
    assert not list(c['store'].root.iterdir())
    await restore(c, dump, baseline)
    for identity, data in files.items():
        c['store'].put(identity, data)
    assert (await c['admin'].get(f'/api/v1/documents/{document}')).status_code == 503
    await replay_deletions(engine=c['owner'], journal=journal, store=c['store'])
    assert (await c['admin'].get(f'/api/v1/documents/{document}')).status_code == 404
    assert not list(c['store'].root.iterdir())
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.chunks WHERE document_id=:id'), {'id': document}) == 0
        assert await connection.scalar(text("SELECT count(*) FROM app.ingestion_jobs WHERE document_id=:id AND status <> 'blocked_policy'"), {'id': document}) == 0


async def test_intent_survives_transaction_failure_and_blocks_release(collections, tmp_path, monkeypatch):
    from docweave.core.settings import deletion_root
    from docweave.storage.artifacts import ArtifactStore
    from docweave.storage.deletions import DeletionJournal
    from docweave.services.deletions import replay_deletions
    c = collections
    chat, _ = await seed_chat(c)
    original = DeletionJournal.record
    def interrupted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise OSError("Simulated failure after durable intent, before database commit")
    monkeypatch.setattr(DeletionJournal, "record", interrupted)
    assert (await c["admin"].delete(f'/api/v1/conversations/{chat}', headers=c["headers"])).status_code == 500
    monkeypatch.setattr(DeletionJournal, "record", original)
    async with c["owner"].connect() as connection:
        assert await connection.scalar(text('SELECT deleted_at IS NULL FROM app.conversations WHERE id=:id'), {"id": UUID(chat)}) is True
    assert (await c["admin"].get(f'/api/v1/conversations/{chat}')).status_code == 503
    await replay_deletions(engine=c["owner"], journal=DeletionJournal(deletion_root()), store=ArtifactStore(tmp_path / "artifacts"))
    assert (await c["admin"].get(f'/api/v1/conversations/{chat}')).status_code == 404


async def test_large_document_history_can_be_deleted_and_partial_batch_replayed(ingestion, monkeypatch):
    from docweave.core.settings import deletion_root
    from docweave.storage.deletions import DeletionJournal
    from docweave.services.deletions import replay_deletions
    c = ingestion
    accepted = (await upload(c)).json()
    await work(c, accepted['job_id'])
    identity = UUID(accepted['document_id'])
    async with c['owner'].begin() as connection:
        configuration = await connection.scalar(text('SELECT configuration FROM app.document_versions WHERE document_id=:id'), {'id': identity})
        await connection.execute(text("""INSERT INTO app.document_versions(document_id,content_hash,configuration)
            SELECT :id,encode(sha256(convert_to(n::text,'UTF8')),'hex'),:configuration FROM generate_series(1,1800) n"""),
            {'id': identity, 'configuration': configuration})
    original = DeletionJournal.record
    calls = 0
    def interrupted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('Failure after first artifact batch')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(DeletionJournal, 'record', interrupted)
    assert (await c['admin'].delete(f'/api/v1/documents/{identity}', headers=c['headers'])).status_code == 500
    monkeypatch.setattr(DeletionJournal, 'record', original)
    journal = DeletionJournal(deletion_root())
    assert len(journal.entries()) == 1
    assert (await c['admin'].get(f'/api/v1/documents/{identity}')).status_code == 503
    await replay_deletions(engine=c['owner'], journal=journal, store=c['store'])
    assert len(journal.entries()) == 4
    assert (await c['admin'].get(f'/api/v1/documents/{identity}')).status_code == 404
    assert not list(c['store'].root.iterdir())


async def test_running_provider_dispatch_rechecks_journal_after_authorization(collections):
    from docweave.core.settings import deletion_root
    from docweave.storage.deletions import DeletionJournal
    from docweave.services.personal_providers import dispatch
    from docweave.integrations.openai import embedding_request
    from docweave.rag.contracts import HostedError
    c = collections
    journal = DeletionJournal(deletion_root())
    async def authorize():
        journal.record('conversation', uuid4(), UUID(c['project']), [])
    with pytest.raises(HostedError, match='deletion_reconciliation_required'):
        await dispatch(embedding_request('Synthetic question', 'query'), embedding=True,
            profile_id=uuid4(), operation_key=str(uuid4())+':query_embedding', actor_id=UUID(c['user']['id']),
            project_id=UUID(c['project']), engine=c['owner'], api_key='fixture', authorize=authorize)
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.cost_reservations')) == 0
