from types import SimpleNamespace
from uuid import uuid4
from contextlib import asynccontextmanager
import pytest


@pytest.mark.anyio
async def test_periodic_worker_recovery_also_reconciles_private_indexes(monkeypatch):
    from docweave.workers import personal
    class Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return None
    engine=SimpleNamespace(begin=lambda:Transaction())
    async def stalled(**kwargs): return []
    queue=SimpleNamespace(job_manager=SimpleNamespace(get_stalled_jobs=stalled))
    events=[]
    async def recover(connection): events.append('personal')
    async def guardrails(actual_engine): events.append(('guardrails',actual_engine))
    async def reconcile(actual_engine,generation): events.append(('private',actual_engine,generation))
    monkeypatch.setattr(personal.repository,'recover_jobs',recover)
    monkeypatch.setattr(personal,'reconcile_rescans',guardrails)
    monkeypatch.setattr(personal,'reconcile_private_indexes',reconcile,raising=False)
    generation=uuid4()
    await personal.recover_jobs(queue,engine,generation)
    assert events==['personal',('guardrails',engine),('private',engine,generation)]


@pytest.mark.anyio
async def test_periodic_recovery_retries_stalled_private_delivery(monkeypatch):
    from docweave.workers import personal
    class Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return None
    engine=SimpleNamespace(begin=lambda:Transaction())
    async def stalled(**kwargs): return [SimpleNamespace(id=42,task_name='docweave.private_index')]
    queue=SimpleNamespace(job_manager=SimpleNamespace(get_stalled_jobs=stalled))
    retried=[]
    async def retry(connection,identity): retried.append(identity)
    async def recover(connection): return None
    async def guardrails(actual_engine): return None
    monkeypatch.setattr(personal.repository,'retry_stalled',retry)
    monkeypatch.setattr(personal.repository,'recover_jobs',recover)
    monkeypatch.setattr(personal,'reconcile_rescans',guardrails)
    await personal.recover_jobs(queue,engine)
    assert retried==[42]


@pytest.mark.anyio
@pytest.mark.parametrize('kind', ['personal', 'catalog', 'private_index', 'guardrail_rescan'])
async def test_every_queue_body_requires_current_retention_before_private_work(monkeypatch, tmp_path, kind):
    from sqlalchemy import make_url
    from docweave.workers import personal
    registered, observed = {}, []
    healthy = False
    identity = uuid4()
    class Engine:
        async def dispose(self): pass
    engine = Engine()
    class Queue:
        def task(self, *, name, **kwargs):
            def register(function):
                registered[name] = function
                return function
            return register
        @asynccontextmanager
        async def open_async(self): yield
        async def run_worker_async(self, **kwargs):
            nonlocal healthy
            with pytest.raises(ValueError, match='Unhealthy retention'):
                await registered['docweave.'+kind](str(identity))
            assert not observed
            healthy = True
            await registered['docweave.'+kind](str(identity))
    async def current(actual_engine, *, artifact_root):
        assert actual_engine is engine and artifact_root == tmp_path
        if not healthy:
            raise ValueError('Unhealthy retention')
    async def clear(*args, **kwargs): return None
    async def recover(*args, **kwargs): return True
    async def overdue(*args, **kwargs): return False
    async def body(actual_identity, **kwargs): observed.append(actual_identity)
    monkeypatch.setattr(personal.GitHubSettings, 'load', lambda: object())
    monkeypatch.setattr(personal, 'GitHubClient', lambda settings: object())
    monkeypatch.setattr(personal, 'database_url', lambda *args: make_url('postgresql+asyncpg://fixture@127.0.0.1:55433/docweave_test'))
    monkeypatch.setattr(personal, 'make_engine', lambda url: engine)
    monkeypatch.setattr(personal, 'storage_root', lambda: tmp_path)
    monkeypatch.setattr(personal.procrastinate, 'PsycopgConnector', lambda **kwargs: None)
    monkeypatch.setattr(personal.procrastinate, 'App', lambda **kwargs: Queue())
    monkeypatch.setattr(personal, 'assert_reconciled', clear)
    monkeypatch.setattr(personal, 'assert_current', current, raising=False)
    monkeypatch.setattr(personal, 'recover_jobs', recover)
    monkeypatch.setattr(personal, 'overdue', overdue)
    monkeypatch.setattr(personal, 'mark', lambda *args, **kwargs: None)
    for name in ('run_personal_job', 'run_catalog_job', 'run_private_index_job', 'run_rescan'):
        monkeypatch.setattr(personal, name, body)
    await personal.run_worker(once=True)
    assert observed == [identity]
