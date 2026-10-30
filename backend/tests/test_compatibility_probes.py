"""Synthetic probe admission is operator-only, durable and capped across workspaces."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from docweave.auth import digest
from docweave.db import tenant_session
from test_budget import allowance, profile, reserve
from test_database import A, B, PA, PB, WA, WB, databases, test_urls  # noqa: F401

pytestmark = pytest.mark.anyio
PAYLOAD = digest("fixed-synthetic-request-v1")


async def register(owner, identity, key="probe-one"):
    async with owner.begin() as connection:
        await connection.execute(text("""INSERT INTO app.compatibility_requests(operation_hash,request_hash,profile_id,input_tokens,output_tokens)
            VALUES (:key,:request,:profile,1,0)"""), {"key": digest(key), "request": PAYLOAD, "profile": identity})


async def claim(engine, key="probe-one", request=PAYLOAD, *, actor=A, workspace=WA, project=PA):
    async with tenant_session(engine, actor_id=actor, workspace_id=workspace) as session:
        return await session.scalar(text("SELECT app.claim_compatibility_probe(:key,:request,:project)"),
            {"key": digest(key), "request": request, "project": project})


async def setup(owner, **overrides):
    identity = await profile(owner, role="embedding", fixed=Decimal("0.01"), enabled=False, account=False, capabilities=False, **overrides)
    await allowance(owner, amount="20")
    await register(owner, identity)
    return identity


async def test_unverified_probe_is_claimed_once_and_retains_uncertainty_before_egress(databases):
    owner, _ = databases
    identity = await setup(owner)
    results = await asyncio.gather(*(claim(owner) for _ in range(3)))
    assert sum(value["created"] for value in results) == 1
    assert len({value["reservation"]["id"] for value in results}) == 1
    assert all(value["reservation"]["status"] == "uncertain" for value in results)
    async with owner.connect() as connection:
        assert (await connection.execute(text("SELECT enabled,account_verified,capabilities_verified FROM app.provider_profiles WHERE id=:id"), {"id": identity})).one() == (False, False, False)


async def test_runtime_cannot_use_probe_exception_or_read_private_journal(databases):
    from docweave.budget import BudgetError
    owner, runtime = databases
    identity = await setup(owner)
    with pytest.raises(BudgetError, match="profile_unavailable"):
        await reserve(runtime, identity, "probe-one", input_tokens=1, output_tokens=0)
    for statement in ("SELECT * FROM app.compatibility_requests", "SELECT * FROM app.compatibility_operations",
        "SELECT app.claim_compatibility_probe(NULL,NULL,NULL)"):
        with pytest.raises(DBAPIError) as error:
            async with runtime.connect() as connection:
                await connection.execute(text(statement))
        assert error.value.orig.sqlstate == "42501"


async def test_payload_hash_or_unregistered_operation_cannot_dispatch(databases):
    owner, _ = databases
    await setup(owner)
    for values in ({"request": digest("different-payload")}, {"key": "unregistered"}):
        with pytest.raises(DBAPIError) as error:
            await claim(owner, **values)
        assert error.value.orig.sqlstate == "DW014"
    assert (await claim(owner))["created"]


async def test_lifetime_probe_cap_is_serialized_across_workspaces(databases):
    owner, _ = databases
    identity = await setup(owner)
    await allowance(owner, WB, "20")
    for number in range(26):
        await register(owner, identity, f"cap-{number}")
    results = await asyncio.gather(*(claim(owner, f"cap-{number}", actor=A if number % 2 else B,
        workspace=WA if number % 2 else WB, project=PA if number % 2 else PB) for number in range(26)), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 25
    assert [value.orig.sqlstate for value in results if isinstance(value, DBAPIError)] == ["DW016"]
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT sum(maximum_usd) FROM app.cost_reservations")) == Decimal("0.25")


async def test_result_reconciliation_does_not_grant_another_dispatch(databases):
    owner, _ = databases
    await setup(owner)
    operation = await claim(owner)
    async with tenant_session(owner, actor_id=A, workspace_id=WA) as session:
        await session.execute(text("SELECT app.complete_compatibility_probe(:id,CAST(:result AS jsonb),:cost,false)"),
            {"id": operation["reservation"]["id"], "result": '{"outcome":"succeeded","dimensions":768}', "cost": Decimal("0.001")})
    replay = await claim(owner)
    assert not replay["created"] and replay["result"] == {"outcome": "succeeded", "dimensions": 768}
    assert replay["reservation"]["charged_usd"] == "0.001000000000"
