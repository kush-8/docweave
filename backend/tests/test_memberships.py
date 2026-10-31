"""Invitation/member boundaries and races use authenticated restricted-role requests."""

import asyncio
from datetime import datetime
from datetime import timezone
from urllib.parse import urlsplit
from uuid import UUID
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_auth import ORIGIN
from test_auth import auth_client
from test_auth import login  # noqa: F401
from test_database import A
from test_database import WA
from test_database import databases
from test_database import test_urls  # noqa: F401
from test_workspaces import signed_in

pytestmark = pytest.mark.anyio


@pytest.fixture
async def members(auth_client):
    admin, data, owner, user, headers = await signed_in(auth_client)
    workspace = (await admin.post("/api/v1/workspaces", json={"name": "Private team"}, headers=headers)).json()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=data["app"], raise_app_exceptions=False), base_url=ORIGIN) as guest:
        data["claims"] = {"sub": "invitee", "email": "recipient@example.com", "name": "Recipient"}
        assert (await login(guest, data)).status_code == 302
        recipient = (await guest.get("/api/v1/me")).json()
        yield {"admin": admin, "guest": guest, "owner": owner, "runtime": data["app"].state.auth[1],
            "user": user, "recipient": recipient, "workspace": workspace, "headers": headers,
            "guest_headers": {"Origin": ORIGIN, "X-CSRF-Token": recipient["csrf_token"]}, "data": data}


async def invite(members, role="member", email="recipient@example.com"):
    response = await members["admin"].post(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations',
        json={"email": email, "role": role}, headers=members["headers"])
    assert response.status_code == 201, response.text
    return response.json()


async def accept(members, invitation):
    return await members["guest"].post(urlsplit(invitation["acceptance_url"]).path, headers=members["guest_headers"])


async def test_invitation_is_hashed_recipient_bound_and_single_use(members):
    created = await invite(members, email="Recipient@EXAMPLE.COM")
    metadata = created["invitation"]
    token = urlsplit(created["acceptance_url"]).path.split("/")[-2]
    assert metadata["status"] == "pending" and metadata["role"] == "member"
    expiry = datetime.fromisoformat(metadata["expires_at"].replace("Z", "+00:00"))
    assert 47.99 < (expiry - datetime.now(timezone.utc)).total_seconds() / 3600 <= 48
    async with members["owner"].connect() as connection:
        row = (await connection.execute(text("SELECT token_hash FROM app.invitations WHERE id=:id"), {"id": UUID(metadata["id"])})).one()
        assert token not in str(row) and len(row.token_hash) == 64
    path = f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations'
    listing = await members["admin"].get(path)
    assert listing.json() == {"items": [metadata], "next_cursor": None}
    assert token not in listing.text and "token_hash" not in listing.text and "acceptance_url" not in listing.text
    wrong = await members["admin"].post(urlsplit(created["acceptance_url"]).path, headers=members["headers"])
    assert wrong.status_code == 404
    response = await accept(members, created)
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == members["recipient"]["id"]
    assert response.json()["role"] == "member"
    assert (await accept(members, created)).status_code == 404
    assert (await members["admin"].get(path)).json()["items"][0]["status"] == "accepted"


async def test_members_can_be_listed_changed_and_removed_by_current_owner(members):
    await accept(members, await invite(members))
    root = f'/api/v1/workspaces/{members["workspace"]["id"]}/members'
    listing = await members["admin"].get(root)
    assert listing.status_code == 200
    assert {m["user_id"] for m in listing.json()["items"]} == {members["user"]["id"], members["recipient"]["id"]}
    assert all(set(m) == {"workspace_id", "user_id", "role", "display_name"} for m in listing.json()["items"])
    target = root + "/" + members["recipient"]["id"]
    updated = await members["admin"].patch(target, json={"role": "maintainer"}, headers=members["headers"])
    assert updated.status_code == 200 and updated.json()["role"] == "maintainer"
    assert (await members["guest"].get("/api/v1/workspaces")).json()["items"][0]["role"] == "maintainer"
    assert (await members["guest"].get(root)).status_code == 403
    assert (await members["admin"].delete(target, headers=members["headers"])).status_code == 204
    assert (await members["guest"].get("/api/v1/workspaces")).json()["items"] == []
    assert (await members["guest"].get(root)).status_code == 404


@pytest.mark.parametrize("action", ["remove", "demote"])
async def test_last_owner_cannot_be_removed_or_demoted(members, action):
    target = f'/api/v1/workspaces/{members["workspace"]["id"]}/members/{members["user"]["id"]}'
    response = await (members["admin"].delete(target, headers=members["headers"]) if action == "remove"
        else members["admin"].patch(target, json={"role": "member"}, headers=members["headers"]))
    assert response.status_code == 409 and response.json()["code"] == "last_owner"
    assert (await members["admin"].patch(target, json={"role": "owner"}, headers=members["headers"])).status_code == 200


@pytest.mark.parametrize("action", ["remove", "demote"])
async def test_concurrent_owner_self_changes_preserve_one_owner(members, action):
    assert (await accept(members, await invite(members, role="owner"))).status_code == 200
    root = f'/api/v1/workspaces/{members["workspace"]["id"]}/members/'
    async def change(client, user, headers):
        if action == "remove":
            return await client.delete(root + user["id"], headers=headers)
        return await client.patch(root + user["id"], json={"role": "member"}, headers=headers)
    responses = await asyncio.gather(change(members["admin"], members["user"], members["headers"]),
        change(members["guest"], members["recipient"], members["guest_headers"]))
    assert sorted(r.status_code for r in responses) == ([204, 409] if action == "remove" else [200, 409])
    async with members["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.memberships WHERE workspace_id=:w AND role='owner'"),
            {"w": UUID(members["workspace"]["id"])}) == 1


async def test_concurrent_acceptance_consumes_once(members):
    created = await invite(members)
    responses = await asyncio.gather(accept(members, created), accept(members, created))
    assert sorted(response.status_code for response in responses) == [200, 404]
    async with members["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.memberships WHERE workspace_id=:w AND user_id=:u"),
            {"w": UUID(members["workspace"]["id"]), "u": UUID(members["recipient"]["id"])}) == 1


@pytest.mark.parametrize("state", ["expired", "revoked"])
async def test_expired_and_revoked_invitations_are_not_accepted(members, state):
    created = await invite(members)
    if state == "expired":
        async with members["owner"].begin() as connection:
            await connection.execute(text("UPDATE app.invitations SET expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),
                {"id": UUID(created["invitation"]["id"])})
    else:
        response = await members["admin"].delete(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations/{created["invitation"]["id"]}', headers=members["headers"])
        assert response.status_code == 204
    response = await accept(members, created)
    assert response.status_code == 404 and response.json()["code"] == "not_found"
    listing = (await members["admin"].get(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations')).json()
    assert listing["items"][0]["status"] == state


async def test_existing_member_acceptance_never_escalates_role_or_consumes_token(members):
    assert (await accept(members, await invite(members))).status_code == 200
    created = await invite(members, role="owner")
    response = await accept(members, created)
    assert response.status_code == 409 and response.json()["code"] == "already_member"
    assert (await members["guest"].get("/api/v1/workspaces")).json()["items"][0]["role"] == "member"
    async with members["owner"].connect() as connection:
        assert await connection.scalar(text("SELECT consumed_at FROM app.invitations WHERE id=:id"),
            {"id": UUID(created["invitation"]["id"])}) is None


@pytest.mark.parametrize("body", [{"email": "bad", "role": "member"}, {"email": "recipient@example.com", "role": "admin"},
    {"email": "recipient@example.com"}, {"email": "x\x00@example.com", "role": "member"},
    {"email": "recipient@example.com", "role": "member", "expires_at": "2099-01-01"}])
async def test_invitation_input_is_validated(members, body):
    response = await members["admin"].post(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations', json=body, headers=members["headers"])
    assert response.status_code == 422


async def test_ownership_and_csrf_cannot_be_supplied_or_bypassed(members):
    root = f'/api/v1/workspaces/{members["workspace"]["id"]}'
    assert (await members["admin"].post(root + "/invitations", json={"email": "recipient@example.com", "role": "member"})).status_code == 403
    assert (await members["guest"].get(root + "/members")).status_code == 404
    assert (await members["guest"].post(root + "/invitations", json={"email": "x@example.com", "role": "owner"}, headers=members["guest_headers"])).status_code == 404
    created = await invite(members)
    assert (await members["guest"].post(urlsplit(created["acceptance_url"]).path)).status_code == 403
    members["guest"].cookies.clear()
    assert (await accept(members, created)).status_code == 401


async def test_invite_ids_are_workspace_scoped_and_fake_tokens_stay_safe(members):
    created = await invite(members)
    for path in [f'/api/v1/workspaces/{WA}/invitations/{created["invitation"]["id"]}',
                 f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations/{uuid4()}']:
        assert (await members["admin"].delete(path, headers=members["headers"])).status_code == 404
    for token in ("private-marker", "a" * 43):
        response = await members["guest"].post(f"/api/v1/invitations/{token}/accept", headers=members["guest_headers"])
        assert response.status_code == 404 and token not in response.text
    assert (await accept(members, created)).status_code == 200


@pytest.mark.parametrize("action", ["remove", "demote"])
async def test_issuer_losing_ownership_revokes_their_pending_invitations(members, action):
    assert (await accept(members, await invite(members, role="owner"))).status_code == 200
    pending = await invite(members, email="later@example.com")
    target = f'/api/v1/workspaces/{members["workspace"]["id"]}/members/{members["user"]["id"]}'
    if action == "remove":
        assert (await members["guest"].delete(target, headers=members["guest_headers"])).status_code == 204
    else:
        assert (await members["guest"].patch(target, json={"role": "member"}, headers=members["guest_headers"])).status_code == 200
    listing = await members["guest"].get(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations')
    assert next(i for i in listing.json()["items"] if i["id"] == pending["invitation"]["id"])["status"] == "revoked"
    assert (await members["admin"].get(f'/api/v1/workspaces/{members["workspace"]["id"]}/members')).status_code == (404 if action == "remove" else 403)


async def test_member_and_invitation_pagination_is_scoped_and_never_returns_secrets(members):
    created = [await invite(members, email=f"recipient{index}@example.com") for index in range(3)]
    root = f'/api/v1/workspaces/{members["workspace"]["id"]}'
    first = (await members["admin"].get(root + "/invitations?limit=2")).json()
    second = (await members["admin"].get(root + "/invitations", params={"cursor": first["next_cursor"], "limit": 2})).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1 and second["next_cursor"] is None
    assert {i["id"] for i in first["items"] + second["items"]} == {i["invitation"]["id"] for i in created}
    assert (await members["admin"].get(root + "/members", params={"cursor": first["next_cursor"]})).status_code == 400
    other = (await members["admin"].post("/api/v1/workspaces", json={"name": "Other"}, headers=members["headers"])).json()
    assert (await members["admin"].get(f'/api/v1/workspaces/{other["id"]}/invitations', params={"cursor": first["next_cursor"]})).status_code == 400
    assert (await accept(members, await invite(members))).status_code == 200
    first = (await members["admin"].get(root + "/members?limit=1")).json()
    second = (await members["admin"].get(root + "/members", params={"cursor": first["next_cursor"], "limit": 1})).json()
    assert len(first["items"]) == len(second["items"]) == 1 and second["next_cursor"] is None


@pytest.mark.parametrize("body", [{}, {"role": None}, {"role": "admin"}, {"role": "member", "user_id": str(A)}])
async def test_member_role_input_is_strict(members, body):
    response = await members["admin"].patch(f'/api/v1/workspaces/{members["workspace"]["id"]}/members/{members["user"]["id"]}',
        json=body, headers=members["headers"])
    assert response.status_code == 422


async def test_unverified_recipient_cannot_consume_invitation(members):
    created = await invite(members)
    async with members["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.users SET email_verified=false WHERE id=:id"), {"id": UUID(members["recipient"]["id"])})
    assert (await accept(members, created)).status_code == 401
    async with members["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.users SET email_verified=true WHERE id=:id"), {"id": UUID(members["recipient"]["id"])})
    assert (await accept(members, created)).status_code == 200


async def wait_for_lock(observer, operation):
    for _ in range(100):
        await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
        waiting = await observer.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE usename='docweave_runtime'
                AND wait_event_type='Lock' AND query LIKE :operation)
        """), {"operation": "%app." + operation + "%"})
        if waiting:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Request never reached the held workspace lock")


async def test_acceptance_rechecks_expiry_after_waiting_for_workspace_lock(members):
    created = await invite(members)
    task = None
    try:
        async with members["owner"].begin() as connection, members["runtime"].connect() as observer:
            await connection.execute(text("SELECT id FROM app.workspaces WHERE id=:id FOR UPDATE"), {"id": UUID(members["workspace"]["id"])})
            task = asyncio.create_task(accept(members, created))
            await wait_for_lock(observer, "accept_invitation")
            await connection.execute(text("UPDATE app.invitations SET expires_at=clock_timestamp() WHERE id=:id"),
                {"id": UUID(created["invitation"]["id"])})
        assert (await task).status_code == 404
    finally:
        if task is not None and not task.done():
            await task


async def test_queued_invitation_creation_rechecks_owner_after_workspace_lock(members):
    assert (await accept(members, await invite(members, role="owner"))).status_code == 200
    task = None
    try:
        async with members["owner"].begin() as connection, members["runtime"].connect() as observer:
            await connection.execute(text("SELECT id FROM app.workspaces WHERE id=:id FOR UPDATE"), {"id": UUID(members["workspace"]["id"])})
            task = asyncio.create_task(members["admin"].post(f'/api/v1/workspaces/{members["workspace"]["id"]}/invitations',
                json={"email": "later@example.com", "role": "member"}, headers=members["headers"]))
            await wait_for_lock(observer, "create_invitation")
            await connection.execute(text("UPDATE app.memberships SET role='member' WHERE workspace_id=:w AND user_id=:u"),
                {"w": UUID(members["workspace"]["id"]), "u": UUID(members["user"]["id"])})
        response = await task
        assert response.status_code == 403 and response.json()["code"] == "forbidden"
        async with members["owner"].connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM app.invitations WHERE workspace_id=:w AND email='later@example.com'"),
                {"w": UUID(members["workspace"]["id"])}) == 0
    finally:
        if task is not None and not task.done():
            await task


async def test_mutation_functions_recheck_revoked_owner_authority(members):
    from docweave.db.sessions import tenant_session

    assert (await accept(members, await invite(members, role="owner"))).status_code == 200
    path = f'/api/v1/workspaces/{members["workspace"]["id"]}/members/{members["user"]["id"]}'
    assert (await members["guest"].patch(path, json={"role": "member"}, headers=members["guest_headers"])).status_code == 200
    with pytest.raises(DBAPIError) as error:
        async with tenant_session(members["runtime"], actor_id=UUID(members["user"]["id"]), workspace_id=UUID(members["workspace"]["id"])) as session:
            await session.execute(text("SELECT * FROM app.create_invitation('later@example.com','member',repeat('a',64))"))
    assert error.value.orig.sqlstate == "42501"


async def test_invitation_storage_and_helper_are_not_directly_accessible_to_runtime(members):
    for statement in ("SELECT * FROM app.invitations", "DELETE FROM app.invitations", "SELECT app.lock_workspace_owner()"):
        with pytest.raises(DBAPIError) as error:
            async with members["runtime"].begin() as connection:
                await connection.execute(text(statement))
        assert error.value.orig.sqlstate == "42501"
    async with members["owner"].connect() as connection:
        rows = (await connection.execute(text("""
            SELECT p.proname,p.proconfig,NOT EXISTS (
                SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
            ) AS no_public FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='app' AND p.proname IN ('lock_workspace_owner','list_members','change_member',
                'create_invitation','list_invitations','revoke_invitation','accept_invitation')
        """))).all()
        assert len(rows) == 7
        assert all(row.no_public and row.proconfig == ["search_path=pg_catalog, app"] for row in rows)
