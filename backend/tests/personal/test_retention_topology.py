import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import text

from tests.support.personal import collections, github_login  # noqa: F401
from tests.database.test_database import databases, test_urls  # noqa: F401
from tests.paths import REPO_ROOT
from tests.rag.test_ingestion import ingestion, upload, work  # noqa: F401
from tests.personal.test_private_indexing import private_index, run  # noqa: F401
from docweave.core.settings import database_url
from docweave.db.engine import make_engine

pytestmark = pytest.mark.anyio


def worker_environment(tmp_path, store):
    from tests.database.test_database import checked_test_urls
    runtime = database_url('TEST_DATABASE_URL').render_as_string(hide_password=False)
    worker = database_url('TEST_WORKER_DATABASE_URL').render_as_string(hide_password=False)
    observer = database_url('TEST_MIGRATION_DATABASE_URL').render_as_string(hide_password=False)
    development = database_url('DATABASE_URL').render_as_string(hide_password=False)
    checked_test_urls(runtime, worker, development)
    checked_test_urls(runtime, observer, development)
    root = tmp_path / 'worker-root'
    root.mkdir()
    (root / 'backups').mkdir()
    return {**os.environ, 'PYTHONPATH': str(REPO_ROOT / 'backend' / 'src'),
        'WORKER_DATABASE_URL': worker, 'DATABASE_URL': runtime, 'RETENTION_OBSERVER_URL': observer,
        'RETENTION_TEST_ROOT': str(root), 'RETENTION_RESULT': str(tmp_path / 'observed.json'),
        'INGESTION_STORAGE_ROOT': str(store), 'RAG_GENERATION_ID': '',
        'OPENAI_API_KEY': '', 'GROQ_API_KEY': '', 'GEMINI_API_KEY': '', 'GOOGLE_API_KEY': '',
        'APP_ORIGIN': 'http://127.0.0.1:5173', 'AUTH_LOCALHOST_HTTP': 'true',
        'GITHUB_CLIENT_ID': 'retention-fixture', 'GITHUB_CLIENT_SECRET': 'fixture',
        'AUTH_ENCRYPTION_KEY': Fernet.generate_key().decode(), 'GITHUB_APP_SLUG': ''}


WORKER = r'''
import asyncio,json,os,sys
from pathlib import Path
from sqlalchemy import text,make_url
from docweave.workers import personal
from docweave.db.engine import make_engine
personal.ROOT=Path(os.environ['RETENTION_TEST_ROOT'])
async def observe(job_id,**kwargs):
    url=make_url(os.environ['RETENTION_OBSERVER_URL'])
    assert (url.host,url.port,url.database)==('127.0.0.1',55433,'docweave_test')
    engine=make_engine(url)
    try:
        async with engine.begin() as c:
            await c.execute(text('SET TRANSACTION READ ONLY'))
            row=(await c.execute(text("""SELECT
                (SELECT count(*) FROM app.turns t JOIN app.conversations c ON c.id=t.conversation_id WHERE c.deleted_at<now()-interval '1 day' AND t.message<>'') chats,
                (SELECT count(*) FROM app.auth_flows WHERE expires_at<now()-interval '1 day') flows,
                (SELECT count(*) FROM app.auth_sessions WHERE expires_at<now()-interval '1 day') sessions,
                (SELECT count(*) FROM app.auth_rate_limits WHERE resets_at<now()-interval '1 day') rate_limits"""))).mappings().one()
            Path(os.environ['RETENTION_RESULT']).write_text(json.dumps(dict(row)))
    finally: await engine.dispose()
personal.run_personal_job=observe
asyncio.run(personal.run_worker(once=os.environ.get('RETENTION_WAIT')!='true'),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)
'''


async def child(environment):
    return await asyncio.to_thread(subprocess.run, [sys.executable, '-c', WORKER], env=environment,
        cwd=REPO_ROOT, capture_output=True, timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)


async def old_chats(c, count):
    async with c['owner'].begin() as connection:
        await connection.execute(text("""WITH chats AS (
            INSERT INTO app.conversations(project_id,status,deleted_at,summary,progress)
            SELECT :project,'deleted',now()-interval '2 days','{"text":"Synthetic old summary"}','Synthetic old progress'
            FROM generate_series(1,:count) RETURNING id)
            INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message,status)
            SELECT id,1,gen_random_uuid(),'Synthetic old question','completed' FROM chats"""),
            {'project': UUID(c['project']), 'count': count})


async def test_startup_drains_overdue_backlog_before_accepting_queue_work(collections, tmp_path):
    from docweave.db.sessions import domain_session
    from docweave.repositories import personal
    c = collections
    await old_chats(c, 205)
    async with c['owner'].begin() as connection:
        for table, column, prefix in (('auth_flows','expires_at','flow'),('auth_sessions','expires_at','session'),('auth_rate_limits','resets_at','rate')):
            identity = "encode(sha256(convert_to(:prefix||n::text,'UTF8')),'hex')"
            if table == 'auth_flows':
                query = f"INSERT INTO app.{table}(state_hash,browser_hash,encrypted_data,{column}) SELECT {identity},{identity},'synthetic',now()-interval '2 days' FROM generate_series(1,205)n"
            elif table == 'auth_sessions':
                query = f"INSERT INTO app.{table}(token_hash,user_id,encrypted_token,{column}) SELECT {identity},:actor,'synthetic',now()-interval '2 days' FROM generate_series(1,205)n"
            else:
                query = f"INSERT INTO app.{table}(bucket,attempts,{column}) SELECT {identity},1,now()-interval '2 days' FROM generate_series(1,205)n"
            await connection.execute(text(query), {'prefix': 'retention-'+prefix, 'actor': UUID(c['user']['id'])})
    async with domain_session(c['runtime'], UUID(c['user']['id'])) as connection:
        await personal.create_conversation(connection, UUID(c['project']), None)
    store = tmp_path / 'artifacts'
    store.mkdir()
    environment = worker_environment(tmp_path, store)
    result = await child(environment)
    assert result.returncode == 0, 'Isolated worker failed; inspect private stderr'
    assert json.loads(Path(environment['RETENTION_RESULT']).read_text()) == {'chats': 0, 'flows': 0, 'sessions': 0, 'rate_limits': 0}


async def test_private_requests_are_held_until_overdue_cleanup_finishes(collections):
    c = collections
    await old_chats(c, 1)
    response = await c['admin'].get(f'/api/v1/projects/{c["project"]}')
    assert response.status_code == 503


async def test_sweep_erases_checkpoint_only_tombstones_without_losing_claims(collections):
    from tests.providers.test_budget import profile
    from docweave.repositories import personal
    c = collections
    selected = await profile(c['owner'], enabled=False)
    async with c['owner'].begin() as connection:
        chat = await connection.scalar(text("INSERT INTO app.conversations(project_id,status,deleted_at) VALUES(:project,'deleted',now()-interval '2 days') RETURNING id"), {'project': UUID(c['project'])})
        job = await connection.scalar(text("INSERT INTO app.personal_jobs(conversation_id,actor_id,kind,status) VALUES(:chat,:actor,'answer','completed') RETURNING id"), {'chat': chat, 'actor': UUID(c['user']['id'])})
        for stage in ('summarization','query_resolution','query_embedding','reranking','generation'):
            key = hashlib.sha256((str(job)+':'+stage).encode()).hexdigest()
            claim = await connection.scalar(text("""INSERT INTO app.cost_reservations(actor_id,project_id,profile_id,operation_hash,month,input_tokens,output_tokens,maximum_usd,status)
                VALUES(:actor,:project,:profile,:key,date_trunc('month',now()),1,1,0.123456789012,'uncertain') RETURNING id"""),
                {'actor': UUID(c['user']['id']), 'project': UUID(c['project']), 'profile': selected, 'key': key})
            await connection.execute(text("""INSERT INTO app.personal_provider_calls(operation_hash,body_hash,key_hash,response,reservation_id)
                VALUES(:key,:key,:key,'{"private":"Synthetic retained answer"}',:claim)"""), {'key': key, 'claim': claim})
        before = list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars())
        calls_before = list((await connection.execute(text("SELECT to_jsonb(c)-'response' FROM app.personal_provider_calls c ORDER BY operation_hash"))).scalars())
    worker = make_engine(database_url('TEST_WORKER_DATABASE_URL'))
    try:
        async with worker.begin() as connection:
            await personal.recover_jobs(connection)
        async with c['owner'].connect() as connection:
            assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls WHERE response IS NOT NULL')) == 0
            assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars()) == before
            assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls')) == 5
            assert list((await connection.execute(text("SELECT to_jsonb(c)-'response' FROM app.personal_provider_calls c ORDER BY operation_hash"))).scalars()) == calls_before
    finally:
        await worker.dispose()


async def protected_claim(c):
    from tests.providers.test_budget import profile
    selected = await profile(c['owner'], enabled=False)
    async with c['owner'].begin() as connection:
        await connection.execute(text("""INSERT INTO app.cost_reservations(actor_id,project_id,profile_id,operation_hash,
            month,input_tokens,output_tokens,maximum_usd,status) VALUES(:actor,:project,:profile,:key,
            date_trunc('month',now()),1,1,0.123456789012,'uncertain')"""),
            {'actor': UUID(c['user']['id']), 'project': UUID(c['project']), 'profile': selected, 'key': 'f'*64})
        return list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars())


@pytest.mark.skipif(sys.platform != 'win32', reason='Exercises actual Windows file-sharing deletion failure')
async def test_actual_orphan_file_lock_stops_worker_then_restart_cleans_safely(ingestion, tmp_path):
    c = ingestion
    accepted = (await upload(c)).json()
    await work(c, accepted['job_id'])
    retained = {path.name: path.read_bytes() for path in c['store'].root.iterdir()}
    before = await protected_claim(c)
    orphan, recent = c['store'].root / str(uuid4()), c['store'].root / str(uuid4())
    orphan.write_bytes(b'Synthetic old orphan')
    recent.write_bytes(b'Synthetic recent uncommitted write')
    os.utime(orphan, (0, 0))
    environment = worker_environment(tmp_path, c['store'].root)
    with orphan.open('rb'):
        with pytest.raises(PermissionError):
            orphan.unlink()
        first = await child(environment)
    assert first.returncode != 0
    locked_error = b'PermissionError' in first.stderr
    assert locked_error, 'Expected actual sharing-lock failure; inspect private stderr'
    assert orphan.exists()
    assert (await c['admin'].get(f'/api/v1/projects/{c["project"]}')).status_code == 503
    second = await child(environment)
    assert second.returncode == 0, 'Restarted isolated worker failed; inspect private stderr'
    assert not orphan.exists() and recent.exists()
    assert (await c['admin'].get(f'/api/v1/projects/{c["project"]}')).status_code == 200
    assert {name: (c['store'].root / name).read_bytes() for name in retained} == retained
    async with c['owner'].connect() as connection:
        assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars()) == before


@pytest.mark.skipif(sys.platform != 'win32', reason='Exercises actual Windows backup-file sharing lock')
async def test_sealed_backup_lock_reports_pending_then_restart_finishes_expiry(ingestion, tmp_path):
    from datetime import datetime, timedelta, timezone
    from docweave.storage.backups import enroll_backup
    c = ingestion
    before = await protected_claim(c)
    environment = worker_environment(tmp_path, c['store'].root)
    backups = Path(environment['RETENTION_TEST_ROOT']) / 'backups'
    folder = backups / 'synthetic-sealed-backup'
    folder.mkdir()
    dump = folder / 'development.dump'
    dump.write_bytes(b'Synthetic recovery fixture')
    (folder / 'acceptance.json').write_text(json.dumps({'restored_before_migration': True,
        'rows_match_rehearsal': True, 'artifacts_preserved': True,
        'backup_sha256': hashlib.sha256(dump.read_bytes()).hexdigest()}))
    enroll_backup(backups, folder.name, created_at=datetime.now(timezone.utc) - timedelta(days=8))
    with dump.open('rb'):
        first = await child(environment)
    assert first.returncode == 0
    reports = [json.loads(line) for line in first.stdout.decode().splitlines() if line.startswith('{"backup_retention"')]
    assert reports == [{'backup_retention': [{'backup': folder.name, 'status': 'retry_pending'}]}]
    assert folder.exists()
    second = await child(environment)
    assert second.returncode == 0
    assert not folder.exists()
    async with c['owner'].connect() as connection:
        assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars()) == before


async def test_running_worker_drains_overdue_backlog_on_next_maintenance_tick(collections, tmp_path):
    c = collections
    store = tmp_path / 'artifacts'
    store.mkdir()
    environment = {**worker_environment(tmp_path, store), 'RETENTION_WAIT': 'true'}
    async def wait_for(predicate, timeout):
        async with asyncio.timeout(timeout):
            while not await predicate():
                assert process.poll() is None, 'Retention worker exited; inspect its private log'
                await asyncio.sleep(0.1)
    async def started():
        async with c['owner'].connect() as connection:
            return await connection.scalar(text("SELECT EXISTS(SELECT 1 FROM queue.procrastinate_workers WHERE last_heartbeat>clock_timestamp()-interval '10 seconds')"))
    orphan = store / str(uuid4())
    async def cleaned():
        async with c['owner'].connect() as connection:
            remaining = await connection.scalar(text("SELECT count(*) FROM app.turns t JOIN app.conversations c ON c.id=t.conversation_id WHERE c.deleted_at IS NOT NULL AND t.message<>''"))
        return remaining == 0 and not orphan.exists()
    with (tmp_path / 'periodic-worker.log').open('wb') as log:
        process = subprocess.Popen([sys.executable, '-c', WORKER], env=environment, cwd=REPO_ROOT,
            stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            await wait_for(started, 15)
            await old_chats(c, 205)
            orphan.write_bytes(b'Synthetic overdue orphan added after startup')
            os.utime(orphan, (0, 0))
            assert (await c['admin'].get(f'/api/v1/projects/{c["project"]}')).status_code == 503
            await wait_for(cleaned, 20)
            assert (await c['admin'].get(f'/api/v1/projects/{c["project"]}')).status_code == 200
        finally:
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(process.wait, 5)


async def test_document_deletion_erases_private_embedding_checkpoint_and_title(private_index, monkeypatch):
    c = private_index
    c['data']['app'].state.ingestion_store = c['store']
    async def provider(*args, **kwargs):
        return {'embedding': {'values': [1.0]+[0.0]*767}}
    monkeypatch.setattr('docweave.services.personal_providers.provider_post', provider)
    await run(c)
    async with c['owner'].connect() as connection:
        before = list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars())
        identities = list((await connection.execute(text("SELECT to_jsonb(c)-'response' FROM app.personal_provider_calls c ORDER BY operation_hash"))).scalars())
        assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls WHERE response IS NOT NULL')) == 1
    response = await c['admin'].delete(f'/api/v1/documents/{c["document"]}', headers=c['headers'])
    assert response.status_code == 202, response.text
    async with c['owner'].connect() as connection:
        assert await connection.scalar(text('SELECT count(*) FROM app.personal_provider_calls WHERE response IS NOT NULL')) == 0
        assert await connection.scalar(text('SELECT title FROM app.documents WHERE id=:id'), {'id': c['document']}) == 'Deleted document'
        assert list((await connection.execute(text('SELECT to_jsonb(r) FROM app.cost_reservations r ORDER BY id'))).scalars()) == before
        assert list((await connection.execute(text("SELECT to_jsonb(c)-'response' FROM app.personal_provider_calls c ORDER BY operation_hash"))).scalars()) == identities
