from types import SimpleNamespace
from uuid import uuid4
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
