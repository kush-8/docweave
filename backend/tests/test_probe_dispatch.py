"""A committed one-time claim precedes every fixed synthetic HTTP request."""

import hashlib
import asyncio
import gzip
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from docweave.auth import digest
from docweave.hosted import synthetic_request
from docweave.policy import Actor
from test_budget import allowance
from test_database import A, PA, WA, databases, test_urls  # noqa: F401
from test_retrieval import basis

pytestmark = pytest.mark.anyio


async def prepare(owner):
    payload = json.dumps(synthetic_request("gemini-query"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    identity = uuid4()
    async with owner.begin() as connection:
        await connection.execute(text("""INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,
            input_usd_per_million,output_usd_per_million,fixed_usd,max_input_tokens,max_output_tokens,pricing_verified)
            VALUES(:id,'gemini','gemini-embedding-2','google-generativelanguage','embedding','[]',0.2,0,0,8192,0,true)"""), {"id": identity})
        await connection.execute(text("""INSERT INTO app.compatibility_requests(operation_hash,request_hash,profile_id,input_tokens,output_tokens)
            VALUES(:key,:hash,:profile,8192,0)"""), {"key": digest("dispatch-v1"), "hash": hashlib.sha256(payload).hexdigest(), "profile": identity})
    await allowance(owner)
    return payload


async def run(owner, handler):
    from docweave.compatibility import run_synthetic_probe
    return await run_synthetic_probe(Actor(A, WA), PA, "gemini-query", "dispatch-v1", engine=owner,
        api_key="synthetic-test-key", transport=httpx.MockTransport(handler))


async def test_http_sees_committed_uncertainty_and_replay_never_dispatches(databases):
    owner, _ = databases
    body = await prepare(owner)
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.content == body
        assert request.url.host == "generativelanguage.googleapis.com"
        async with owner.connect() as connection:
            assert await connection.scalar(text("SELECT status FROM app.cost_reservations")) == "uncertain"
        return httpx.Response(200, json={"embedding": {"values": basis()}})
    result = await run(owner, handler)
    assert result["outcome"] == "succeeded" and result["dimensions"] == 768
    assert await run(owner, handler) == result
    assert len(calls) == 1


async def test_timeout_is_retained_and_never_replayed(databases):
    owner, _ = databases
    await prepare(owner)
    calls = []
    async def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-provider-diagnostic")
    result = await run(owner, handler)
    assert result == {"outcome": "completion_unknown", "failure": "transport_uncertain"}
    assert await run(owner, handler) == result and len(calls) == 1


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "https://elsewhere.invalid"}),
    httpx.Response(200, content=b"x" * 131073), httpx.Response(200, json={"embedding": {"values": [0.0] * 768}})])
async def test_redirect_oversize_and_invalid_response_fail_without_retry(databases, response):
    owner, _ = databases
    await prepare(owner)
    calls = []
    async def handler(request):
        calls.append(request)
        return response
    assert (await run(owner, handler))["outcome"] == "rejected"
    await run(owner, handler)
    assert len(calls) == 1


async def test_changed_registered_body_cannot_reach_transport(databases):
    from docweave.hosted import HostedError
    owner, _ = databases
    await prepare(owner)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.compatibility_requests SET request_hash=repeat('a',64)"))
    async def handler(request):
        pytest.fail("Unregistered request reached transport")
    with pytest.raises(HostedError, match="probe_configuration_mismatch"):
        await run(owner, handler)


async def test_lost_claim_acknowledgement_never_replays_http(databases, monkeypatch):
    import docweave.compatibility as module
    owner, _ = databases
    await prepare(owner)
    original = module.tenant_session
    @asynccontextmanager
    async def lost_ack(*args, **kwargs):
        async with original(*args, **kwargs) as session:
            yield session
        raise OSError("simulated lost commit acknowledgement")
    async def handler(request):
        pytest.fail("Unacknowledged claim reached HTTP")
    with monkeypatch.context() as patch:
        patch.setattr(module, "tenant_session", lost_ack)
        with pytest.raises(OSError):
            await run(owner, handler)
    assert await run(owner, handler) == {"outcome": "completion_unknown", "failure": "previous_dispatch_unresolved"}


async def test_cancellation_preserves_unknown_execution_without_replay(databases):
    owner, _ = databases
    await prepare(owner)
    calls = []
    async def handler(request):
        calls.append(request)
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await run(owner, handler)
    assert await run(owner, handler) == {"outcome": "completion_unknown", "failure": "previous_dispatch_unresolved"}
    assert len(calls) == 1


async def test_operator_preparation_is_idempotent_and_does_not_enable_profiles(databases):
    from docweave.compatibility import prepare_synthetic_probes
    owner, _ = databases
    first = await prepare_synthetic_probes(owner)
    second = await prepare_synthetic_probes(owner)
    assert first == second and len(first["operations"]) == 4
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.compatibility_requests")) == 4
        assert await connection.scalar(text("SELECT count(*) FROM app.provider_profiles WHERE enabled OR account_verified OR capabilities_verified")) == 0
        assert await connection.scalar(text("SELECT count(*) FROM app.cost_reservations")) == 0


async def test_registration_bounds_are_checked_after_budget_lock_wait(databases):
    from docweave.hosted import HostedError
    owner, _ = databases
    await prepare(owner)
    async def handler(request):
        pytest.fail("Changed reservation bounds reached HTTP")
    async with owner.connect() as lock, owner.connect() as observer:
        transaction = await lock.begin()
        await lock.execute(text("SELECT app.lock_budget()"))
        task = asyncio.create_task(run(owner, handler))
        try:
            for _ in range(100):
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                if await observer.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='docweave_migrator' AND wait_event_type='Lock')")):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Probe never reached the budget lock")
            await lock.execute(text("UPDATE app.compatibility_requests SET input_tokens=1"))
            await transaction.commit()
            with pytest.raises(HostedError, match="probe_configuration_mismatch"):
                await task
        finally:
            if transaction.is_active:
                await transaction.rollback()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_compressed_provider_response_is_rejected_before_decoding(databases):
    owner, _ = databases
    await prepare(owner)
    async def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"},
            content=gzip.compress(json.dumps({"embedding": {"values": basis()}}).encode()))
    assert await run(owner, handler) == {"outcome": "rejected", "failure": "provider_response_encoding"}
