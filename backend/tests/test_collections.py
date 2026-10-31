"""Current collection grants and separate processor consent through real PostgreSQL."""

import asyncio
import json
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_auth import auth_client  # noqa: F401
from test_database import B
from test_database import PB
from test_database import WB
from test_database import databases
from test_database import test_urls  # noqa: F401
from test_memberships import accept
from test_memberships import invite
from test_memberships import members
from test_memberships import wait_for_lock  # noqa: F401
from test_projects import validate

pytestmark = pytest.mark.anyio
PROCESSORS = [
    ("test:gemini:embedding:v1", "gemini", "test-google", '["embedding"]'),
    ("test:gemini:reranking:v1", "gemini", "test-google", '["reranking"]'),
    ("test:groq:generation:v1", "groq", "test-groq", '["generation"]'),
]


@pytest.fixture
async def collections(members):
    result = await members["admin"].post(f'/api/v1/workspaces/{members["workspace"]["id"]}/projects',
        json={"name": "Private project", "goal": "Cited support", "stack": [{"technology": "FastAPI"}]}, headers=members["headers"])
    assert result.status_code == 201, result.text
    project = result.json()["project"]
    assert (await accept(members, await invite(members))).status_code == 200
    return {**members, "project": project["id"], "collection": project["default_collection_id"]}


def grant_path(c):
    return f'/api/v1/collections/{c["collection"]}/grants'


def policy_path(c, kind):
    return f'/api/v1/{"projects" if kind == "project" else "collections"}/{c[kind]}/processing-policy'


async def replace_grants(c, grants, revision=1):
    return await c["admin"].put(grant_path(c), json={"expected_revision": revision, "grants": grants}, headers=c["headers"])


async def configure_processors(c):
    async with c["owner"].begin() as connection:
        for identity, provider, backend, roles in PROCESSORS:
            await connection.execute(text("""
                INSERT INTO app.processors(id,provider,backend,roles) VALUES (:id,:provider,:backend,CAST(:roles AS jsonb)) ON CONFLICT DO NOTHING
            """), {"id": identity, "provider": provider, "backend": backend, "roles": roles})
            await connection.execute(text("UPDATE app.processors SET enabled=true WHERE id=:id"), {"id": identity})


async def test_collections_start_owner_only_and_list_only_current_grants(collections):
    c = collections
    path = f'/api/v1/projects/{c["project"]}/collections'
    listed = await c["admin"].get(path)
    assert listed.status_code == 200, listed.text
    validate("CollectionPage", listed.json())
    assert listed.json()["items"] == [{"id": c["collection"], "project_id": c["project"], "name": "Default", "can_write": True}]
    assert (await c["guest"].get(path)).json() == {"items": [], "next_cursor": None}
    created = await c["admin"].post(path, json={"name": "  Secret manuals  "}, headers=c["headers"])
    assert created.status_code == 201, created.text
    validate("Collection", created.json())
    assert created.json()["name"] == "Secret manuals" and created.json()["can_write"]
    assert (await c["guest"].post(path, json={"name": "No"}, headers=c["guest_headers"])).status_code == 403
    for collection in (c["collection"], created.json()["id"]):
        assert (await c["guest"].get(f"/api/v1/collections/{collection}/processing-policy")).status_code == 404


async def test_read_grants_never_elevate_member_and_writer_needs_maintainer_role(collections):
    c = collections
    user = c["recipient"]["id"]
    assert (await c["admin"].get(grant_path(c))).json() == {"revision": 1, "grants": []}
    invalid = await replace_grants(c, [{"user_id": user, "access": "write"}])
    assert invalid.status_code == 422
    read = await replace_grants(c, [{"user_id": user, "access": "read"}])
    assert read.status_code == 200, read.text
    validate("GrantSet", read.json())
    assert read.json()["revision"] == 2
    path = f'/api/v1/projects/{c["project"]}/collections'
    assert (await c["guest"].get(path)).json()["items"][0]["can_write"] is False
    documents = f'/api/v1/collections/{c["collection"]}/documents'
    assert (await c["guest"].get(documents)).json() == {"items": [], "next_cursor": None}
    assert (await c["guest"].post(documents, headers=c["guest_headers"])).status_code == 403
    member = f'/api/v1/workspaces/{c["workspace"]["id"]}/members/{user}'
    assert (await c["admin"].patch(member, json={"role": "maintainer"}, headers=c["headers"])).status_code == 200
    written = await replace_grants(c, [{"user_id": user, "access": "write"}], 2)
    assert written.status_code == 200, written.text
    assert (await c["guest"].post(documents, headers=c["guest_headers"])).status_code == 422
    assert (await c["guest"].get(path)).json()["items"][0]["can_write"] is True
    assert (await c["guest"].get(grant_path(c))).status_code == 403
    assert (await c["guest"].put(grant_path(c), json={"expected_revision": 3, "grants": []}, headers=c["guest_headers"])).status_code == 403


@pytest.mark.parametrize("change", ["demote", "remove"])
async def test_membership_changes_reconcile_grants_and_never_resurrect_write_access(collections, change):
    c = collections
    user = c["recipient"]["id"]
    member = f'/api/v1/workspaces/{c["workspace"]["id"]}/members/{user}'
    await c["admin"].patch(member, json={"role": "maintainer"}, headers=c["headers"])
    assert (await replace_grants(c, [{"user_id": user, "access": "write"}])).status_code == 200
    if change == "demote":
        assert (await c["admin"].patch(member, json={"role": "member"}, headers=c["headers"])).status_code == 200
        grants = (await c["admin"].get(grant_path(c))).json()
        assert grants == {"revision": 3, "grants": [{"user_id": user, "access": "read"}]}
        await c["admin"].patch(member, json={"role": "maintainer"}, headers=c["headers"])
        assert (await c["guest"].post(f'/api/v1/collections/{c["collection"]}/documents', headers=c["guest_headers"])).status_code == 403
    else:
        assert (await c["admin"].delete(member, headers=c["headers"])).status_code == 204
        assert (await c["admin"].get(grant_path(c))).json() == {"revision": 3, "grants": []}
        assert (await accept(c, await invite(c, role="maintainer"))).status_code == 200
        assert (await c["guest"].get(policy_path(c, "collection"))).status_code == 404
    stale = await replace_grants(c, [], revision=2)
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"


@pytest.mark.parametrize("grants", [
    [{"user_id": str(uuid4()), "access": "read"}], [{"user_id": str(B), "access": "read"}],
    [{"user_id": "bad", "access": "read"}], [{"user_id": str(B), "access": "admin"}],
    [{"user_id": str(B), "access": "read", "role": "owner"}], None,
])
async def test_invalid_grants_preserve_previous_set(collections, grants):
    c = collections
    prior = await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    assert prior.status_code == 200, prior.text
    assert (await replace_grants(c, grants, revision=2)).status_code == 422
    assert (await c["admin"].get(grant_path(c))).json() == prior.json()


async def test_duplicate_grants_and_bad_revisions_are_rejected(collections):
    c = collections
    grant = {"user_id": c["recipient"]["id"], "access": "read"}
    for body in [{"expected_revision": 1, "grants": [grant, grant]}, {"expected_revision": True, "grants": []},
        {"expected_revision": "1", "grants": []}, {"expected_revision": 0, "grants": []}, {"grants": []},
        {"expected_revision": 1, "grants": [], "workspace_id": str(WB)}]:
        assert (await c["admin"].put(grant_path(c), json=body, headers=c["headers"])).status_code == 422


@pytest.mark.parametrize("kind", ["project", "collection"])
async def test_processor_consent_is_configured_revisioned_and_revocable(collections, kind):
    c = collections
    path = policy_path(c, kind)
    assert (await c["admin"].get(path)).json() == {"revision": 1, "approved_processor_ids": []}
    await configure_processors(c)
    selected = [PROCESSORS[2][0]]
    response = await c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": selected}, headers=c["headers"])
    assert response.status_code == 200, response.text
    validate("ProcessingPolicy", response.json())
    assert response.json() == {"revision": 2, "approved_processor_ids": selected}
    other = "collection" if kind == "project" else "project"
    assert (await c["admin"].get(policy_path(c, other))).json() == {"revision": 1, "approved_processor_ids": []}
    stale = await c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": []}, headers=c["headers"])
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    cleared = await c["admin"].put(path, json={"expected_revision": 2, "approved_processor_ids": []}, headers=c["headers"])
    assert cleared.json() == {"revision": 3, "approved_processor_ids": []}


@pytest.mark.parametrize("ids", [["gemini"], ["unknown-backend"], [""], ["A\x00B"], [None], None, ["duplicate", "duplicate"]])
async def test_invalid_processor_ids_do_not_change_consent(collections, ids):
    c = collections
    for kind in ("project", "collection"):
        path = policy_path(c, kind)
        response = await c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": ids}, headers=c["headers"])
        assert response.status_code == 422, response.text
        assert (await c["admin"].get(path)).json() == {"revision": 1, "approved_processor_ids": []}


async def test_reading_consent_requires_scope_access_and_changing_it_requires_owner(collections):
    c = collections
    assert (await c["guest"].get(policy_path(c, "project"))).json() == {"revision": 1, "approved_processor_ids": []}
    assert (await c["guest"].get(policy_path(c, "collection"))).status_code == 404
    await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    assert (await c["guest"].get(policy_path(c, "collection"))).json() == {"revision": 1, "approved_processor_ids": []}
    for kind in ("project", "collection"):
        assert (await c["guest"].put(policy_path(c, kind), json={"expected_revision": 1, "approved_processor_ids": []}, headers=c["guest_headers"])).status_code == 403
    await replace_grants(c, [], 2)
    assert (await c["guest"].get(policy_path(c, "collection"))).status_code == 404


async def test_hidden_other_tenant_and_malformed_ids_do_not_leak(collections):
    c = collections
    async with c["owner"].connect() as connection:
        other = await connection.scalar(text("SELECT id FROM app.collections WHERE workspace_id=:w"), {"w": WB})
    for identity in (other, uuid4(), "not-a-uuid"):
        for suffix in ("grants", "processing-policy", "documents"):
            response = await c["admin"].get(f"/api/v1/collections/{identity}/{suffix}", headers={"X-Actor-ID": str(B), "X-Workspace-ID": str(WB)})
            assert response.status_code == 404 and response.json()["code"] == "not_found"
            assert "Default" not in response.text
    assert (await c["admin"].get(f"/api/v1/projects/{PB}/processing-policy")).status_code == 404


@pytest.mark.parametrize("operation", ["grants", "project", "collection"])
async def test_concurrent_policy_replacements_have_one_winner(collections, operation):
    c = collections
    path = grant_path(c) if operation == "grants" else policy_path(c, operation)
    key = "grants" if operation == "grants" else "approved_processor_ids"
    responses = await asyncio.gather(*(c["admin"].put(path, json={"expected_revision": 1, key: []}, headers=c["headers"]) for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (await c["admin"].get(path)).json()["revision"] == 2


async def test_collection_pagination_rechecks_grants_and_rejects_cross_resource_cursor(collections):
    c = collections
    path = f'/api/v1/projects/{c["project"]}/collections'
    for name in ("Second", "Third"):
        assert (await c["admin"].post(path, json={"name": name}, headers=c["headers"])).status_code == 201
    first = (await c["admin"].get(path, params={"limit": 1})).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = (await c["admin"].get(path, params={"cursor": first["next_cursor"]})).json()
    assert len(second["items"]) == 2 and second["next_cursor"] is None
    assert (await c["admin"].get("/api/v1/workspaces", params={"cursor": first["next_cursor"]})).status_code == 400
    await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])
    assert (await c["guest"].get(path, params={"cursor": first["next_cursor"]})).status_code == 400
    await replace_grants(c, [], 2)
    assert (await c["guest"].get(path)).json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("operation", ["create", "grants", "project", "collection"])
async def test_mutations_require_csrf_and_recheck_owner_after_lock_wait(collections, operation):
    c = collections
    if operation == "create":
        path, method, body, query = f'/api/v1/projects/{c["project"]}/collections', "POST", {"name": "Queued"}, "create_collection"
    elif operation == "grants":
        path, method, body, query = grant_path(c), "PUT", {"expected_revision": 1, "grants": []}, "replace_collection_grants"
    else:
        path, method, body, query = policy_path(c, operation), "PUT", {"expected_revision": 1, "approved_processor_ids": []}, "replace_processing_policy"
    assert (await c["admin"].request(method, path, json=body)).status_code == 403
    task = None
    try:
        async with c["owner"].begin() as lock:
            await lock.execute(text("SELECT id FROM app.workspaces WHERE id=:w FOR UPDATE"), {"w": UUID(c["workspace"]["id"])})
            task = asyncio.create_task(c["admin"].request(method, path, json=body, headers=c["headers"]))
            async with c["runtime"].connect() as observer:
                await wait_for_lock(observer, query)
            await lock.execute(text("UPDATE app.memberships SET role='member' WHERE workspace_id=:w AND user_id=:u"),
                {"w": UUID(c["workspace"]["id"]), "u": UUID(c["user"]["id"])})
        assert (await task).status_code == 403
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_registry_identity_is_immutable_and_disabled_processors_cannot_be_approved(collections):
    c = collections
    assert (await c["admin"].get(policy_path(c, "project"))).status_code == 200
    await configure_processors(c)
    for statement in ["UPDATE app.processors SET backend='different' WHERE id=:id", "DELETE FROM app.processors WHERE id=:id"]:
        with pytest.raises(DBAPIError) as error:
            async with c["owner"].begin() as connection:
                await connection.execute(text(statement), {"id": PROCESSORS[0][0]})
        assert error.value.orig.sqlstate == "22023"
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.processors SET enabled=false WHERE id=:id"), {"id": PROCESSORS[0][0]})
    denied = await c["admin"].put(policy_path(c, "project"), json={"expected_revision": 1,
        "approved_processor_ids": [PROCESSORS[0][0]]}, headers=c["headers"])
    assert denied.status_code == 422


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": " \t\n"}, {"name": None}, {"name": "A\x00B"},
    {"name": "Secret", "workspace_id": str(WB)}])
async def test_collection_creation_rejects_invalid_input_without_writing(collections, body):
    c = collections
    path = f'/api/v1/projects/{c["project"]}/collections'
    response = await c["admin"].post(path, json=body, headers=c["headers"])
    assert response.status_code == 422, response.text
    assert len((await c["admin"].get(path)).json()["items"]) == 1


async def test_storage_permissions_and_function_search_paths_are_restricted(collections):
    from docweave.db.sessions import tenant_session

    c = collections
    async with c["owner"].connect() as connection:
        rows = (await connection.execute(text("""
            SELECT p.proname,p.prosecdef,p.proconfig,has_function_privilege('docweave_runtime',p.oid,'EXECUTE') AS runtime,
                NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                    WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS no_public
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='app'
                AND p.proname IN ('immutable_processor','reconcile_member_grants','collection_can','collection_workspace',
                    'create_collection','collection_grants','replace_collection_grants','processing_policy','replace_processing_policy')
        """))).all()
        assert len(rows) == 9
        assert all(r.no_public and r.proconfig == ["search_path=pg_catalog, app"] for r in rows)
        assert all(r.runtime == r.prosecdef == (r.proname not in {"immutable_processor", "reconcile_member_grants"}) for r in rows)
    statements = ["SELECT * FROM app.collection_grants", "SELECT * FROM app.project_processor_approvals",
        "SELECT * FROM app.collection_processor_approvals", "DELETE FROM app.collections",
        "INSERT INTO app.processors(id,provider,backend,roles) VALUES ('forged','gemini','forged','[\"embedding\"]')",
        "UPDATE app.processors SET enabled=true", "SELECT app.reconcile_member_grants() IS NULL", "SELECT app.immutable_processor() IS NULL"]
    for statement in statements:
        with pytest.raises(DBAPIError) as error:
            async with tenant_session(c["runtime"], actor_id=UUID(c["user"]["id"]), workspace_id=UUID(c["workspace"]["id"])) as session:
                await session.execute(text(statement))
        assert error.value.orig.sqlstate == "42501", statement
    async with c["runtime"].connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.collections")) == 0


async def test_runtime_cannot_bypass_owner_checks_or_selected_workspace(collections):
    from docweave.db.sessions import tenant_session

    c = collections
    statements = ["SELECT app.create_collection(:project,'No')", "SELECT app.collection_grants(:collection)",
        "SELECT app.replace_collection_grants(:collection,1,'[]'::jsonb)",
        "SELECT app.replace_processing_policy('project',:project,1,'[]'::jsonb)",
        "SELECT app.replace_processing_policy('collection',:collection,1,'[]'::jsonb)"]
    args = {"project": UUID(c["project"]), "collection": UUID(c["collection"])}
    for statement in statements:
        with pytest.raises(DBAPIError) as error:
            async with tenant_session(c["runtime"], actor_id=UUID(c["recipient"]["id"]), workspace_id=UUID(c["workspace"]["id"])) as session:
                await session.execute(text(statement), args)
        assert error.value.orig.sqlstate == "42501"
    with pytest.raises(DBAPIError) as error:
        async with tenant_session(c["runtime"], actor_id=UUID(c["user"]["id"]), workspace_id=UUID(c["workspace"]["id"])) as session:
            await session.execute(text("SELECT app.create_collection(:project,'Other tenant')"), {"project": PB})
    assert error.value.orig.sqlstate == "P0002"


@pytest.mark.parametrize("kind", ["project", "collection"])
async def test_processor_disabled_while_waiting_is_rejected_and_revocation_remains_possible(collections, kind):
    c = collections
    await configure_processors(c)
    path = policy_path(c, kind)
    selected = [PROCESSORS[0][0]]
    task = None
    try:
        async with c["owner"].begin() as lock:
            await lock.execute(text("SELECT id FROM app.processors WHERE id=:id FOR UPDATE"), {"id": selected[0]})
            task = asyncio.create_task(c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": selected}, headers=c["headers"]))
            async with c["runtime"].connect() as observer:
                await wait_for_lock(observer, "replace_processing_policy")
            await lock.execute(text("UPDATE app.processors SET enabled=false WHERE id=:id"), {"id": selected[0]})
        assert (await task).status_code == 422
        assert (await c["admin"].get(path)).json() == {"revision": 1, "approved_processor_ids": []}
        await configure_processors(c)
        assert (await c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": selected}, headers=c["headers"])).status_code == 200
        async with c["owner"].begin() as connection:
            await connection.execute(text("UPDATE app.processors SET enabled=false WHERE id=:id"), {"id": selected[0]})
        assert (await c["admin"].put(path, json={"expected_revision": 2, "approved_processor_ids": []}, headers=c["headers"])).json() == {"revision": 3, "approved_processor_ids": []}
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("operation", ["grants", "project", "collection"])
async def test_insert_failure_restores_previous_rows_and_revision(collections, operation):
    c = collections
    if operation == "grants":
        path, key, values, table = grant_path(c), "grants", [{"user_id": c["recipient"]["id"], "access": "read"}], "collection_grants"
    else:
        await configure_processors(c)
        path, key, values, table = policy_path(c, operation), "approved_processor_ids", [PROCESSORS[0][0]], f"{operation}_processor_approvals"
    first = await c["admin"].put(path, json={"expected_revision": 1, key: values}, headers=c["headers"])
    assert first.status_code == 200, first.text
    async with c["owner"].begin() as connection:
        await connection.execute(text("""CREATE FUNCTION app.test_reject_policy_insert() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private failure marker'; END $$"""))
        await connection.execute(text(f"CREATE TRIGGER test_reject_policy_insert BEFORE INSERT ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.test_reject_policy_insert()"))
    try:
        response = await c["admin"].put(path, json={"expected_revision": 2, key: values}, headers=c["headers"])
        assert response.status_code == 500 and "private failure marker" not in response.text
        assert (await c["admin"].get(path)).json() == first.json()
    finally:
        async with c["owner"].begin() as connection:
            await connection.execute(text(f"DROP TRIGGER test_reject_policy_insert ON app.{table}"))
            await connection.execute(text("DROP FUNCTION app.test_reject_policy_insert()"))


async def test_runtime_openapi_declares_consent_security_and_strict_inputs(collections):
    from jsonschema import Draft202012Validator
    from jsonschema import FormatChecker

    schema = (await collections["admin"].get("/openapi.json")).json()
    for path, method in [("/projects/{project_id}/collections", "post"), ("/collections/{collection_id}/grants", "put"),
        ("/projects/{project_id}/processing-policy", "put"), ("/collections/{collection_id}/processing-policy", "put")]:
        assert schema["paths"]["/api/v1" + path][method]["security"] == [{"sessionCookie": [], "csrfToken": []}]
    policy = schema["paths"]["/api/v1/projects/{project_id}/processing-policy"]["put"]["requestBody"]["content"]["application/json"]["schema"]
    validator = Draft202012Validator({**policy, "components": schema["components"]}, format_checker=FormatChecker())
    assert validator.is_valid({"expected_revision": 1, "approved_processor_ids": []})
    for body in [{"expected_revision": 1, "approved_processor_ids": None}, {"expected_revision": True, "approved_processor_ids": []},
        {"expected_revision": 1, "approved_processor_ids": ["a", "a"]}, {"approved_processor_ids": []}]:
        assert not validator.is_valid(body), body


@pytest.mark.parametrize("operation", ["project", "collection", "revocation"])
async def test_policy_read_keeps_authority_revision_and_ids_in_one_snapshot(collections, operation):
    c = collections
    await configure_processors(c)
    kind = "project" if operation == "project" else "collection"
    path = policy_path(c, kind)
    prior = (await c["admin"].put(path, json={"expected_revision": 1, "approved_processor_ids": [PROCESSORS[0][0]]}, headers=c["headers"])).json()
    assert prior["revision"] == 2
    if operation == "revocation":
        assert (await replace_grants(c, [{"user_id": c["recipient"]["id"], "access": "read"}])).status_code == 200
    reader = c["guest"] if operation == "revocation" else c["admin"]
    task = None
    try:
        async with c["owner"].begin() as lock:
            await lock.execute(text(f"LOCK TABLE app.{kind}_processor_approvals IN ACCESS EXCLUSIVE MODE"))
            task = asyncio.create_task(reader.get(path))
            async with c["runtime"].connect() as observer:
                await wait_for_lock(observer, "processing_policy")
            await lock.execute(text("SELECT set_config('docweave.actor_id',:actor,true),set_config('docweave.workspace_id',:workspace,true)"),
                {"actor": c["user"]["id"], "workspace": c["workspace"]["id"]})
            updated = await lock.scalar(text("SELECT app.replace_processing_policy(:kind,:id,2,CAST(:ids AS jsonb))"),
                {"kind": kind, "id": UUID(c[kind]), "ids": json.dumps([PROCESSORS[2][0]])})
            assert updated == {"revision": 3, "approved_processor_ids": [PROCESSORS[2][0]]}
            if operation == "revocation":
                await lock.execute(text("SELECT app.replace_collection_grants(:id,2,'[]'::jsonb)"), {"id": UUID(c["collection"])})
        response = await task
        if operation == "revocation":
            assert response.status_code == 404 or response.json() == prior
            assert (await reader.get(path)).status_code == 404
        else:
            assert response.status_code == 200
            assert response.json() in (prior, updated)
            assert (await reader.get(path)).json() == updated
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
