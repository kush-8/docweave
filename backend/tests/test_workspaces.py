"""Workspace behavior is exercised through real auth and restricted-role PostgreSQL."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from test_auth import ORIGIN, auth_client, login  # noqa: F401
from test_database import A, WA, WB, databases, test_urls  # noqa: F401

pytestmark = pytest.mark.anyio


async def signed_in(auth_client):
    client, data, owner, settings = auth_client
    assert (await login(client, data)).status_code == 302
    user = (await client.get("/api/v1/me")).json()
    return client, data, owner, user, {"Origin": ORIGIN, "X-CSRF-Token": user["csrf_token"]}


async def test_create_workspace_atomically_adds_only_the_actor_as_owner(auth_client):
    client, _, owner, user, headers = await signed_in(auth_client)
    response = await client.post("/api/v1/workspaces", json={"name": "Engineering"}, headers=headers)
    assert response.status_code == 201, response.text
    workspace = response.json()
    assert set(workspace) == {"id", "name", "role", "created_at"}
    assert workspace["name"] == "Engineering" and workspace["role"] == "owner"
    UUID(workspace["id"])
    assert response.headers["cache-control"] == "no-store"
    async with owner.connect() as connection:
        memberships = (await connection.execute(text("SELECT user_id,role FROM app.memberships WHERE workspace_id=:id"),
            {"id": UUID(workspace["id"])})).all()
        assert memberships == [(UUID(user["id"]), "owner")]
    listed = await client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert listed.json() == {"items": [workspace], "next_cursor": None}


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": " \t\n"}, {"name": "A\x00B"}, {"name": None}, {"name": 5},
    {"name": "Private", "owner_id": str(A)}, {"name": "Private", "role": "owner"}, {"name": "Private", "budget": "99"}])
async def test_workspace_input_is_strict_and_invalid_requests_create_nothing(auth_client, body):
    client, _, owner, _, headers = await signed_in(auth_client)
    response = await client.post("/api/v1/workspaces", json=body, headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert "Private" not in response.text
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.workspaces")) == 2
        assert await connection.scalar(text("SELECT count(*) FROM app.memberships")) == 2


async def test_create_requires_session_and_csrf(auth_client):
    client, _, _, _ = auth_client
    assert (await client.post("/api/v1/workspaces", json={"name": "Private"})).status_code == 401
    client, _, _, _, headers = await signed_in(auth_client)
    for invalid in ({}, {**headers, "Origin": "https://evil.test"}, {**headers, "X-CSRF-Token": "wrong"}):
        assert (await client.post("/api/v1/workspaces", json={"name": "Private"}, headers=invalid)).status_code == 403


async def test_list_is_membership_filtered_and_revocation_applies_next_request(auth_client):
    client, data, owner, _, headers = await signed_in(auth_client)
    assert (await client.get("/api/v1/workspaces")).json() == {"items": [], "next_cursor": None}
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Private Alpha"}, headers=headers)).json()
    data["claims"] = {"sub": "different-person"}
    assert (await login(client, data)).status_code == 302
    other = (await client.get("/api/v1/me")).json()
    assert (await client.get("/api/v1/workspaces")).json() == {"items": [], "next_cursor": None}
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:w,:u,'member')"),
            {"w": UUID(workspace["id"]), "u": UUID(other["id"])})
    page = (await client.get("/api/v1/workspaces")).json()
    assert page["items"] == [{**workspace, "role": "member"}]
    async with owner.begin() as connection:
        await connection.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"),
            {"w": UUID(workspace["id"]), "u": UUID(other["id"])})
    assert (await client.get("/api/v1/workspaces")).json() == {"items": [], "next_cursor": None}


async def seed_workspaces(owner, user_id, count):
    ids = [uuid4() for _ in range(count)]
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.workspaces(id,name,created_at) VALUES (:id,:name,'2026-01-01T00:00:00Z')"),
            [{"id": value, "name": f"Space {index}"} for index, value in enumerate(ids)])
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:w,:u,'member')"),
            [{"w": value, "u": UUID(user_id)} for value in ids])
    return sorted(str(value) for value in ids)


async def test_keyset_pagination_is_stable_for_equal_timestamps_and_defaults_to_25(auth_client):
    client, _, owner, user, _ = await signed_in(auth_client)
    ids = await seed_workspaces(owner, user["id"], 27)
    first = (await client.get("/api/v1/workspaces")).json()
    assert [w["id"] for w in first["items"]] == ids[:25]
    assert first["next_cursor"]
    second = (await client.get("/api/v1/workspaces", params={"cursor": first["next_cursor"], "limit": 2})).json()
    assert [w["id"] for w in second["items"]] == ids[25:]
    assert second["next_cursor"] is None
    assert (await client.get("/api/v1/workspaces", params={"limit": 100})).json()["next_cursor"] is None


async def test_cursors_are_opaque_tamper_resistant_and_actor_bound(auth_client):
    client, data, owner, user, _ = await signed_in(auth_client)
    await seed_workspaces(owner, user["id"], 2)
    cursor = (await client.get("/api/v1/workspaces?limit=1")).json()["next_cursor"]
    assert user["id"] not in cursor and "Space" not in cursor
    changed = cursor[:30] + ("A" if cursor[30] != "A" else "B") + cursor[31:]
    for invalid in ("junk", changed):
        response = await client.get("/api/v1/workspaces", params={"cursor": invalid})
        assert response.status_code == 400 and response.json()["code"] == "invalid_cursor"
    data["claims"] = {"sub": "different-person"}
    assert (await login(client, data)).status_code == 302
    response = await client.get("/api/v1/workspaces", params={"cursor": cursor})
    assert response.status_code == 400 and response.json()["code"] == "invalid_cursor"


async def test_pagination_rechecks_membership_between_pages(auth_client):
    client, _, owner, user, _ = await signed_in(auth_client)
    ids = await seed_workspaces(owner, user["id"], 3)
    first = (await client.get("/api/v1/workspaces?limit=1")).json()
    async with owner.begin() as connection:
        await connection.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"),
            {"w": UUID(ids[1]), "u": UUID(user["id"])})
    response = await client.get("/api/v1/workspaces", params={"cursor": first["next_cursor"]})
    assert [w["id"] for w in response.json()["items"]] == ids[2:]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=no", "cursor=", "cursor=" + "x" * 2049])
async def test_pagination_query_bounds_are_validated(auth_client, query):
    client, _, _, _, _ = await signed_in(auth_client)
    assert (await client.get("/api/v1/workspaces?" + query)).status_code == 422


async def test_workspace_guards_hide_outsiders_and_check_current_owner_role(auth_client):
    client, _, owner, user, headers = await signed_in(auth_client)
    for workspace in (WA, uuid4()):
        response = await client.get(f"/api/v1/workspaces/{workspace}/projects")
        assert response.status_code == 404 and response.json()["code"] == "not_found"
        assert "Alpha" not in response.text
    assert (await client.get("/api/v1/workspaces/not-a-uuid/projects")).status_code == 404
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:w,:u,'owner')"),
            {"w": WA, "u": UUID(user["id"])})
    assert (await client.get(f"/api/v1/workspaces/{WA}/members")).status_code == 200
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.memberships SET role='member' WHERE workspace_id=:w AND user_id=:u"),
            {"w": WA, "u": UUID(user["id"])})
    assert (await client.get(f"/api/v1/workspaces/{WA}/projects")).status_code == 200
    for method, path in [("GET", "members"), ("GET", "invitations"), ("POST", "projects"), ("POST", "invitations")]:
        response = await client.request(method, f"/api/v1/workspaces/{WA}/{path}", headers=headers)
        assert response.status_code == 403 and response.json()["code"] == "forbidden"
    async with owner.begin() as connection:
        await connection.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"),
            {"w": WA, "u": UUID(user["id"])})
    assert (await client.get(f"/api/v1/workspaces/{WA}/projects")).status_code == 404


async def test_actor_contains_only_verified_ids_and_cannot_be_supplied_by_request(auth_client):
    from docweave.policy import Actor

    client, _, owner, user, _ = await signed_in(auth_client)
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:w,:u,'member')"),
            {"w": WA, "u": UUID(user["id"])})
    response = await client.get(f"/api/v1/workspaces/{WB}/projects", headers={"X-Actor-ID": str(A), "X-Workspace-ID": str(WA)},
        params={"user_id": str(A), "workspace_id": str(WA), "role": "owner"})
    assert response.status_code == 404
    assert set(Actor.__dataclass_fields__) == {"user_id", "workspace_id"}


async def test_workspace_creation_rolls_back_if_owner_insert_fails(databases):
    from docweave.db import tenant_session

    owner, runtime = databases
    with pytest.raises(IntegrityError):
        async with tenant_session(runtime, actor_id=uuid4()) as session:
            await session.execute(text("SELECT * FROM app.create_workspace('Must roll back')"))
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.workspaces")) == 2
        assert await connection.scalar(text("SELECT count(*) FROM app.memberships")) == 2


async def test_workspace_functions_do_not_work_without_actor_context(databases):
    _, runtime = databases
    async with runtime.begin() as connection:
        assert (await connection.execute(text("SELECT * FROM app.list_workspaces(NULL,NULL,26)"))).all() == []
    with pytest.raises(DBAPIError) as error:
        async with runtime.begin() as connection:
            await connection.execute(text("SELECT * FROM app.create_workspace('Denied')"))
    assert error.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("signature", ["app.create_workspace(text)", "app.list_workspaces(timestamptz,uuid,integer)"])
async def test_workspace_functions_have_fixed_search_path_and_no_public_execute(databases, signature):
    owner, _ = databases
    async with owner.connect() as connection:
        row = (await connection.execute(text("""
            SELECT prosecdef,proconfig,NOT EXISTS (
                SELECT 1 FROM aclexplode(coalesce(proacl,acldefault('f',proowner))) a
                WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
            ) AS no_public FROM pg_proc WHERE oid=cast(:signature AS regprocedure)
        """), {"signature": signature})).one()
        assert row.prosecdef and row.no_public
        assert row.proconfig == ["search_path=pg_catalog, app"]


async def test_actor_only_context_cannot_read_unselected_tenant_rows_and_clears_on_reuse(databases):
    from docweave.db import tenant_session

    _, runtime = databases
    async with tenant_session(runtime, actor_id=A) as session:
        assert (await session.execute(text("SELECT * FROM app.list_workspaces(NULL,NULL,26)"))).one().id == WA
        for table in ("workspaces", "memberships", "projects"):
            assert await session.scalar(text(f"SELECT count(*) FROM app.{table}")) == 0
    async with runtime.connect() as connection:
        assert not await connection.scalar(text("SELECT current_setting('docweave.actor_id',true)"))
        assert not await connection.scalar(text("SELECT current_setting('docweave.workspace_id',true)"))
