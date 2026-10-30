"""Exact, concurrent budget admission on guarded disposable PostgreSQL only."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_auth import auth_client  # noqa: F401
from test_database import A, B, PA, PB, WA, WB, databases, test_urls  # noqa: F401
from test_projects import validate
from test_memberships import wait_for_lock
from test_workspaces import signed_in

pytestmark = pytest.mark.anyio


async def profile(owner, **overrides):
    args = {"id": uuid4(), "fixed": Decimal("0.6"), "input": Decimal("0"), "output": Decimal("0"),
        "enabled": True, "capabilities": True, "account": True, "pricing": True, "attempts": 1, "role": "generation", **overrides}
    args.setdefault("provider", "gemini" if args["role"] == "embedding" else "groq")
    args.setdefault("backend", "fake-google" if args["provider"] == "gemini" else "fake-groq")
    args.setdefault("processors", ["test:budget:google", "test:budget:groq"] if args["role"] == "generation"
        else ["test:budget:google" if args["provider"] == "gemini" else "test:budget:groq"])
    args["processors"] = json.dumps(args["processors"])
    async with owner.begin() as connection:
        await connection.execute(text("""INSERT INTO app.processors(id,provider,backend,roles)
            VALUES ('test:budget:google','gemini','fake-google','["embedding","reranking","generation"]') ON CONFLICT DO NOTHING"""))
        await connection.execute(text("""INSERT INTO app.processors(id,provider,backend,roles)
            VALUES ('test:budget:groq','groq','fake-groq','["reranking","generation","query_resolution","summarization"]') ON CONFLICT DO NOTHING"""))
        await connection.execute(text("UPDATE app.processors SET enabled=true WHERE id IN ('test:budget:google','test:budget:groq')"))
        await connection.execute(text("""
            INSERT INTO app.provider_profiles(id,provider,model,backend,role,processor_ids,input_usd_per_million,output_usd_per_million,
                fixed_usd,max_input_tokens,max_output_tokens,max_attempts,enabled,capabilities_verified,account_verified,pricing_verified)
            VALUES (:id,:provider,'fake-model',:backend,:role,CAST(:processors AS jsonb),:input,:output,
                :fixed,1000,1000,:attempts,:enabled,:capabilities,:account,:pricing)
        """), args)
    return args["id"]


async def allowance(owner, workspace=WA, amount="1", month=None):
    async with owner.begin() as connection:
        await connection.execute(text("SELECT app.set_workspace_allowance(:w,CAST(:month AS date),CAST(:amount AS numeric))"),
            {"w": workspace, "month": month, "amount": Decimal(amount)})


async def reserve(runtime, identity, key="operation-a", *, actor_id=A, workspace=WA, project=PA, input_tokens=1, output_tokens=1):
    from docweave.budget import reserve_cost
    from docweave.policy import Actor

    return await reserve_cost(Actor(actor_id, workspace), key, identity, input_tokens, output_tokens, engine=runtime, project_id=project)


async def settle(runtime, reservation, actual, uncertain=False, *, actor_id=A, workspace=WA):
    from docweave.budget import settle_cost
    from docweave.policy import Actor

    return await settle_cost(reservation.id, actual, uncertain, actor=Actor(actor_id, workspace), engine=runtime)


async def test_concurrent_reservations_respect_workspace_and_global_caps(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    results = await asyncio.gather(*(reserve(runtime, identity, key) for key in ("first", "second")), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert [r.code for r in results if isinstance(r, BudgetError)] == ["workspace_limit"]
    await allowance(owner, amount="20")
    await allowance(owner, WB, "20")
    expensive = await profile(owner, fixed=Decimal("11"))
    results = await asyncio.gather(reserve(runtime, expensive, "global-a"),
        reserve(runtime, expensive, "global-b", actor_id=B, workspace=WB, project=PB), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert [r.code for r in results if isinstance(r, BudgetError)] == ["application_capacity_unavailable"]


async def test_same_operation_is_idempotent_and_changed_payload_or_actor_conflicts(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    values = await asyncio.gather(reserve(runtime, identity), reserve(runtime, identity))
    assert values[0].id == values[1].id and sorted(r.created for r in values) == [False, True]
    with pytest.raises(BudgetError, match="operation_conflict"):
        await reserve(runtime, identity, input_tokens=2)
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:w,:u,'member')"), {"w": WA, "u": B})
    with pytest.raises(BudgetError, match="operation_conflict"):
        await reserve(runtime, identity, actor_id=B)


async def test_uncertain_settlement_retains_maximum_then_confirmed_reconciliation_is_idempotent(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    reservation = await reserve(runtime, identity)
    assert reservation.maximum_usd == Decimal("0.6") and reservation.status == "reserved"
    unknown = await settle(runtime, reservation, None, True)
    assert unknown.status == "uncertain" and unknown.charged_usd == Decimal("0.6")
    assert (await settle(runtime, reservation, None, True)).charged_usd == Decimal("0.6")
    with pytest.raises(BudgetError, match="workspace_limit"):
        await reserve(runtime, identity, "another")
    confirmed = await settle(runtime, reservation, Decimal("0.2"))
    assert confirmed.status == "metered" and confirmed.charged_usd == Decimal("0.2")
    assert (await settle(runtime, reservation, Decimal("0.2"))).charged_usd == Decimal("0.2")
    with pytest.raises(BudgetError, match="settlement_conflict"):
        await settle(runtime, reservation, Decimal("0.1"))
    assert (await reserve(runtime, identity, "another")).created
    assert (await reserve(runtime, identity)).status == "metered"


@pytest.mark.parametrize("overrides", [{"input": None}, {"fixed": None}, {"enabled": False},
    {"pricing": False}, {"capabilities": False}, {"account": False}])
async def test_unverified_or_unpriced_profiles_cannot_reserve(databases, overrides):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner, **overrides)
    await allowance(owner)
    with pytest.raises(BudgetError, match="profile_unavailable"):
        await reserve(runtime, identity)


async def test_missing_allowance_and_disabled_processor_fail_closed(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    with pytest.raises(BudgetError, match="allowance_required"):
        await reserve(runtime, identity)
    await allowance(owner)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.processors SET enabled=false WHERE id='test:budget:google'"))
    with pytest.raises(BudgetError, match="profile_unavailable"):
        await reserve(runtime, identity)


async def test_decimal_bounds_attempts_and_actual_overrun_are_conservative(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner, fixed=Decimal("0"), input=Decimal("0.0000001"), output=Decimal("0"), attempts=3)
    await allowance(owner)
    reservation = await reserve(runtime, identity)
    assert reservation.maximum_usd == Decimal("0.000000000001")
    result = await settle(runtime, reservation, Decimal("0.0000000000011"))
    assert result.charged_usd == Decimal("0.000000000002")
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT enabled FROM app.provider_profiles WHERE id=:id"), {"id": identity}) is False
    with pytest.raises(BudgetError, match="profile_unavailable"):
        await reserve(runtime, identity, "after-overrun")


async def test_month_uses_calcutta_and_old_charges_do_not_move_on_reconciliation(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    async with runtime.connect() as connection:
        assert await connection.scalar(text("SELECT app.budget_month('2026-10-31 18:29:59+00')")) == date(2026, 10, 1)
        assert await connection.scalar(text("SELECT app.budget_month('2026-10-31 18:30:00+00')")) == date(2026, 11, 1)
    identity = await profile(owner)
    await allowance(owner)
    reservation = await reserve(runtime, identity)
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.cost_reservations SET month='2020-01-01' WHERE id=:id"), {"id": reservation.id})
    assert (await reserve(runtime, identity)).month == date(2020, 1, 1)
    assert (await reserve(runtime, identity, "new-month-operation")).created
    assert (await settle(runtime, reservation, Decimal("0.5"))).month == date(2020, 1, 1)


async def test_settlement_is_scoped_but_can_record_cost_after_membership_revocation(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    reservation = await reserve(runtime, identity)
    with pytest.raises(BudgetError, match="not_found"):
        await settle(runtime, reservation, Decimal("0"), actor_id=B, workspace=WB)
    async with owner.begin() as connection:
        await connection.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"), {"w": WA, "u": A})
    with pytest.raises(BudgetError, match="not_found"):
        await reserve(runtime, identity, "after-revocation")
    assert (await settle(runtime, reservation, Decimal("0.3"))).charged_usd == Decimal("0.3")


@pytest.mark.parametrize("value", [True, -1, 1.5, "1", 1001])
async def test_token_bounds_reject_invalid_values(databases, value):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    with pytest.raises((ValueError, TypeError, BudgetError)):
        await reserve(runtime, identity, input_tokens=value)


async def test_provider_and_usage_apis_are_honest_and_tenant_filtered(auth_client):
    client, _, owner, _, headers = await signed_in(auth_client)
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Budget team"}, headers=headers)).json()["id"]
    response = await client.get("/api/v1/providers")
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None}
    identity = await profile(owner, account=False)
    response = await client.get("/api/v1/providers")
    validate("ProviderPage", response.json())
    assert response.json()["items"][0]["id"] == str(identity)
    assert not response.json()["items"][0]["enabled"] and response.json()["items"][0]["disabled_reason"] == "account_unverified"
    usage = await client.get(f"/api/v1/workspaces/{workspace}/usage")
    assert usage.status_code == 200, usage.text
    validate("UsageReport", usage.json())
    assert usage.json()["workspace_allowance_usd"] is None and usage.json()["capacity_status"] == "allowance_required"
    assert usage.json()["metered_usd"].startswith("0") and "global" not in usage.text
    assert (await client.get(f"/api/v1/workspaces/{WB}/usage")).status_code == 404
    assert (await client.get(f"/api/v1/projects/{PB}/usage")).status_code == 404
    assert (await client.get(f"/api/v1/workspaces/{workspace}/usage?month=0000-01")).status_code == 422


async def test_runtime_cannot_read_ledger_or_raise_caps(databases):
    owner, runtime = databases
    for statement in ["SELECT * FROM app.cost_reservations", "SELECT * FROM app.workspace_allowances",
        "UPDATE app.provider_profiles SET enabled=true", "SELECT app.set_workspace_allowance(:w,NULL,20)"]:
        with pytest.raises(DBAPIError) as error:
            async with runtime.begin() as connection:
                await connection.execute(text(statement), {"w": WA})
        assert error.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("change,code", [("cap", "workspace_limit"), ("membership", "not_found"), ("profile", "profile_unavailable")])
async def test_admission_rechecks_changes_after_budget_lock_wait(databases, change, code):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    task = None
    try:
        async with owner.begin() as lock:
            await lock.execute(text("SELECT app.lock_budget()"))
            task = asyncio.create_task(reserve(runtime, identity))
            async with runtime.connect() as observer:
                await wait_for_lock(observer, "reserve_cost")
            if change == "cap":
                await lock.execute(text("SELECT app.set_workspace_allowance(:w,NULL,0.4)"), {"w": WA})
            elif change == "membership":
                await lock.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"), {"w": WA, "u": A})
            else:
                await lock.execute(text("UPDATE app.provider_profiles SET enabled=false WHERE id=:id"), {"id": identity})
        with pytest.raises(BudgetError, match=code):
            await task
        async with owner.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM app.cost_reservations")) == 0
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_zero_allowance_stops_even_zero_priced_hosted_work(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner, fixed=Decimal("0"))
    await allowance(owner, amount="0")
    with pytest.raises(BudgetError, match="workspace_limit"):
        await reserve(runtime, identity)


@pytest.mark.parametrize("actual", [0.1, True, Decimal("NaN"), Decimal("Infinity"), Decimal("-0.1")])
async def test_invalid_or_binary_float_actual_cost_cannot_change_ledger(databases, actual):
    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    reservation = await reserve(runtime, identity)
    with pytest.raises((ValueError, TypeError)):
        await settle(runtime, reservation, actual)
    assert (await reserve(runtime, identity)).charged_usd == Decimal("0.6")


async def test_uncertain_partial_cost_never_shrinks_and_confirmed_replays_cannot_reopen_it(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner, amount="20")
    reservation = await reserve(runtime, identity)
    assert (await settle(runtime, reservation, Decimal("0.8"), True)).charged_usd == Decimal("0.8")
    assert (await settle(runtime, reservation, None, True)).charged_usd == Decimal("0.8")
    results = await asyncio.gather(settle(runtime, reservation, Decimal("0.4")), settle(runtime, reservation, Decimal("0.4")))
    assert all(r.charged_usd == Decimal("0.4") and r.status == "metered" for r in results)
    with pytest.raises(BudgetError, match="settlement_conflict"):
        await settle(runtime, reservation, None, True)


async def test_overrun_is_recorded_and_stops_future_global_admission(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner, amount="20")
    reservation = await reserve(runtime, identity)
    assert (await settle(runtime, reservation, Decimal("20.01"))).charged_usd == Decimal("20.01")
    another = await profile(owner)
    await allowance(owner, WB, "20")
    with pytest.raises(BudgetError, match="application_capacity_unavailable"):
        await reserve(runtime, another, actor_id=B, workspace=WB, project=PB)


async def test_profiles_are_immutable_and_public_without_a_session(auth_client):
    client, data, owner, _ = auth_client
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await client.get("/api/v1/providers")).json() == {"items": [], "next_cursor": None}
    ids = [await profile(owner) for _ in range(3)]
    first = (await client.get("/api/v1/providers", params={"limit": 2})).json()
    validate("ProviderPage", first)
    assert len(first["items"]) == 2 and first["next_cursor"]
    last = (await client.get("/api/v1/providers", params={"cursor": first["next_cursor"]})).json()
    assert len(last["items"]) == 1 and last["next_cursor"] is None
    assert {p["id"] for p in first["items"] + last["items"]} == {str(i) for i in ids}
    assert all("disabled_reason" not in p for p in first["items"] + last["items"])
    assert data["exchanges"] == []
    for mutation in ["model='another'", "input_usd_per_million=50", "processor_ids='[]'", "max_attempts=10"]:
        with pytest.raises(DBAPIError) as error:
            async with owner.begin() as connection:
                await connection.execute(text(f"UPDATE app.provider_profiles SET {mutation} WHERE id=:id"), {"id": ids[0]})
        assert error.value.orig.sqlstate == "22023"


async def test_usage_totals_project_attribution_and_capacity_never_include_other_tenants(auth_client):
    client, data, owner, user, headers = await signed_in(auth_client)
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Accounting"}, headers=headers)).json()["id"]
    projects = []
    for name in ("One", "Two"):
        projects.append((await client.post(f"/api/v1/workspaces/{workspace}/projects", json={"name": name, "goal": "Test", "stack": [{"technology": "Python"}]}, headers=headers)).json()["project"]["id"])
    identity = await profile(owner)
    await allowance(owner, UUID(workspace))
    runtime = data["app"].state.auth[1]
    args = {"actor_id": UUID(user["id"]), "workspace": UUID(workspace)}
    first = await reserve(runtime, identity, project=UUID(projects[0]), **args)
    await settle(runtime, first, Decimal("0.2"), **args)
    second = await reserve(runtime, identity, "uncertain", project=UUID(projects[1]), **args)
    await settle(runtime, second, None, True, **args)
    await allowance(owner, WB, "20")
    await reserve(runtime, identity, "other-tenant", actor_id=B, workspace=WB, project=PB)
    report = (await client.get(f"/api/v1/workspaces/{workspace}/usage")).json()
    validate("UsageReport", report)
    assert Decimal(report["metered_usd"]) == Decimal("0.2")
    assert Decimal(report["reserved_usd"]) == 0 and Decimal(report["retained_uncertain_usd"]) == Decimal("0.6")
    assert report["capacity_status"] == "available"
    project = (await client.get(f"/api/v1/projects/{projects[0]}/usage")).json()
    validate("UsageReport", project)
    assert Decimal(project["metered_usd"]) == Decimal("0.2") and Decimal(project["retained_uncertain_usd"]) == 0
    await allowance(owner, UUID(workspace), "0.7")
    assert (await client.get(f"/api/v1/workspaces/{workspace}/usage")).json()["capacity_status"] == "workspace_limit"
    for month in ("0000-01", "2026-13", "2026-01-01", "2026-1"):
        assert (await client.get(f"/api/v1/workspaces/{workspace}/usage", params={"month": month})).status_code == 422


async def test_narrow_function_acl_and_current_project_scope(databases):
    from docweave.budget import BudgetError

    owner, runtime = databases
    identity = await profile(owner)
    await allowance(owner)
    with pytest.raises(BudgetError, match="not_found"):
        await reserve(runtime, identity, project=PB)
    async with owner.connect() as connection:
        rows = (await connection.execute(text("""
            SELECT p.proname,p.proconfig,has_function_privilege('docweave_runtime',p.oid,'EXECUTE') AS runtime,
                NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                    WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS no_public
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='app'
                AND p.proname IN ('budget_month','lock_budget','immutable_profile','profile_disabled_reason','set_workspace_allowance',
                    'reservation_view','reserve_cost','settle_cost','usage_report')
        """))).all()
        assert len(rows) == 9
        assert all(r.no_public and r.proconfig == ["search_path=pg_catalog, app"] for r in rows)
        assert all(r.runtime == (r.proname not in {"lock_budget", "immutable_profile", "set_workspace_allowance", "reservation_view"}) for r in rows)


async def test_answer_catalog_does_not_offer_internal_embedding_profiles(auth_client):
    client, data, owner, _ = auth_client
    answer = await profile(owner)
    embedding = await profile(owner, role="embedding")
    response = await client.get("/api/v1/providers")
    assert response.status_code == 200
    assert [p["id"] for p in response.json()["items"]] == [str(answer)]
    await allowance(owner)
    assert (await reserve(data["app"].state.auth[1], embedding, output_tokens=0)).created
