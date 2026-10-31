"""Manual project lifecycle and tenant boundaries through restricted PostgreSQL."""

import asyncio
import json
from uuid import UUID
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from jsonschema import FormatChecker
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_api import DRAFT
from test_auth import auth_client  # noqa: F401
from test_database import B
from test_database import PB
from test_database import WB
from test_database import databases
from test_database import migrate
from test_database import test_urls  # noqa: F401
from test_memberships import wait_for_lock
from test_workspaces import signed_in

pytestmark = pytest.mark.anyio
INPUT = {"name": "Assistant", "goal": "Build cited answers", "stack": [{"technology": "FastAPI", "docs_target": "0.115"}, {"technology": "PostgreSQL"}]}


@pytest.fixture
async def projects(auth_client):
    client, data, owner, user, headers = await signed_in(auth_client)
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Project team"}, headers=headers)).json()
    return client, data, owner, user, headers, workspace["id"]


async def create(projects, body=None):
    client, _, _, _, headers, workspace = projects
    response = await client.post(f"/api/v1/workspaces/{workspace}/projects", json=body or INPUT, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def validate(schema, body):
    Draft202012Validator({"$ref": f"#/components/schemas/{schema}", "components": DRAFT["components"]},
        format_checker=FormatChecker()).validate(body)


async def test_creation_persists_default_collection_and_honest_pending_documentation(projects):
    client, _, owner, user, _, workspace = projects
    created = await create(projects)
    validate("ProjectCreated", created)
    project = created["project"]
    assert project["workspace_id"] == workspace and project["context_revision"] == 1
    assert project["name"] == INPUT["name"] and project["goal"] == INPUT["goal"]
    assert project["source_state"] == "pending_review" and created["job_ids"] == []
    assert created["pending_dependency_ids"] == [dep["id"] for dep in project["stack"]]
    assert [dep["docs_target"] for dep in project["stack"]] == ["0.115", None]
    assert all(dep["declared_version"] is None and dep["resolved_version"] is None for dep in project["stack"])
    async with owner.connect() as connection:
        collection = (await connection.execute(text("SELECT * FROM app.collections WHERE id=:id"),
            {"id": UUID(project["default_collection_id"])})).one()
        assert collection.workspace_id == UUID(workspace) and collection.project_id == UUID(project["id"]) and collection.is_default
        requests = (await connection.execute(text("SELECT * FROM app.documentation_requests WHERE project_id=:p"),
            {"p": UUID(project["id"])})).all()
        assert {str(r.id) for r in requests} == set(created["pending_dependency_ids"])
        assert all(str(r.requested_by) == user["id"] and r.state == "pending_review" and r.context_revision == 1 for r in requests)
    assert (await client.get(f'/api/v1/projects/{project["id"]}')).json() == project
    listing = await client.get(f"/api/v1/workspaces/{workspace}/projects")
    validate("ProjectPage", listing.json())
    assert listing.json() == {"items": [project], "next_cursor": None}
    assert listing.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    {"name": ""}, {"name": " \t\n"}, {"goal": ""}, {"goal": None}, {"name": 5},
    {"stack": []}, {"stack": None}, {"stack": [{"technology": ""}]}, {"stack": [{"technology": "  "}]},
    {"stack": [{"technology": "FastAPI", "docs_target": ""}]}, {"stack": [{"technology": "FastAPI", "docs_target": None}]},
    {"stack": [{"technology": "FastAPI", "resolved_version": "99"}]},
    {"stack_review_id": str(uuid4())}, {"workspace_id": str(WB)}, {"context_revision": 55},
    {"name": "private\x00marker"}, {"goal": "private\x00marker"}, {"environment": "private\x00marker"},
    {"architecture_notes": None}, {"stack": [{"technology": "A\x00B"}]},
])
async def test_invalid_creation_writes_nothing(projects, changes):
    client, _, owner, _, headers, workspace = projects
    response = await client.post(f"/api/v1/workspaces/{workspace}/projects", json={**INPUT, **changes}, headers=headers)
    assert response.status_code == 422, response.text
    assert "private" not in response.text
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.projects WHERE workspace_id=:w"), {"w": UUID(workspace)}) == 0


async def test_missing_stack_and_unimplemented_review_do_not_create_projects(projects):
    client, _, owner, _, headers, workspace = projects
    base = {"name": "Reviewed", "goal": "User supplied"}
    path = f"/api/v1/workspaces/{workspace}/projects"
    assert (await client.post(path, json=base, headers=headers)).status_code == 422
    assert (await client.post(path, json={**base, "stack_review_id": None}, headers=headers)).status_code == 422
    assert (await client.post(path, json={**base, "stack_review_id": str(uuid4())}, headers=headers)).status_code == 501
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.projects WHERE workspace_id=:w"), {"w": UUID(workspace)}) == 0


async def test_patch_preserves_omissions_clears_optional_fields_and_rejects_stale_revision(projects):
    client, _, owner, _, headers, _ = projects
    project = (await create(projects, {**INPUT, "architecture_notes": "layered", "environment": "local", "constraints": "private"}))["project"]
    path = f'/api/v1/projects/{project["id"]}'
    response = await client.patch(path, json={"expected_revision": 1, "goal": "Updated goal", "architecture_notes": ""}, headers=headers)
    assert response.status_code == 200, response.text
    updated = response.json()
    validate("Project", updated)
    assert updated == {**project, "goal": "Updated goal", "architecture_notes": "", "context_revision": 2}
    stale = await client.patch(path, json={"expected_revision": 1, "name": "Lost edit"}, headers=headers)
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    assert (await client.get(path)).json() == updated
    async with owner.connect() as connection:
        assert set((await connection.execute(text("SELECT context_revision FROM app.documentation_requests WHERE project_id=:p"),
            {"p": UUID(project["id"])})).scalars()) == {2}


@pytest.mark.parametrize("body", [{}, {"expected_revision": 1}, {"expected_revision": 0, "goal": "A"},
    {"expected_revision": True, "goal": "A"}, {"expected_revision": "1", "goal": "A"},
    {"expected_revision": 1, "goal": " \n"}, {"expected_revision": 1, "environment": None},
    {"expected_revision": 1, "stack": []}, {"expected_revision": 1, "stack_review_id": str(uuid4())},
    {"expected_revision": 1, "workspace_id": str(WB)}, {"expected_revision": 1, "name": "A\x00B"}])
async def test_patch_input_is_strict(projects, body):
    project = (await create(projects))["project"]
    response = await projects[0].patch(f'/api/v1/projects/{project["id"]}', json=body, headers=projects[4])
    assert response.status_code == 422, response.text


async def test_stack_replacement_supersedes_pending_requests_atomically(projects):
    project = (await create(projects))["project"]
    response = await projects[0].patch(f'/api/v1/projects/{project["id"]}', json={"expected_revision": 1,
        "stack": [{"technology": "Python", "docs_target": "3.12"}]}, headers=projects[4])
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["default_collection_id"] == project["default_collection_id"]
    assert updated["stack"][0]["technology"] == "Python" and updated["context_revision"] == 2
    async with projects[2].connect() as connection:
        rows = (await connection.execute(text("SELECT id,state,context_revision FROM app.documentation_requests WHERE project_id=:p"),
            {"p": UUID(project["id"])})).all()
        assert {str(r.id) for r in rows if r.state == "superseded"} == {d["id"] for d in project["stack"]}
        assert [(str(r.id), r.context_revision) for r in rows if r.state == "pending_review"] == [(updated["stack"][0]["id"], 2)]


async def test_project_and_child_ids_hide_other_workspaces_and_ignore_forged_actor(projects):
    client, _, _, _, headers, _ = projects
    for project in (PB, uuid4(), "not-a-uuid"):
        for suffix in ("", "/collections", "/jobs", "/processing-policy", "/conversations"):
            response = await client.get(f"/api/v1/projects/{project}{suffix}", headers={"X-Actor-ID": str(B), "X-Workspace-ID": str(WB)})
            assert response.status_code == 404 and "Beta" not in response.text
        assert (await client.patch(f"/api/v1/projects/{project}", json={"expected_revision": 1, "goal": "Forged"}, headers=headers)).status_code == 404


@pytest.mark.parametrize("role", ["maintainer", "member"])
async def test_members_can_read_context_but_not_collection_content_or_mutate(projects, role):
    client, data, owner, user, headers, workspace = projects
    project = (await create(projects))["project"]
    from docweave.db.sessions import tenant_session

    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.memberships SET role=:role WHERE workspace_id=:w AND user_id=:u"), {"w": UUID(workspace), "u": UUID(user["id"]), "role": role})
    assert (await client.get(f'/api/v1/projects/{project["id"]}')).json() == project
    assert len((await client.get(f"/api/v1/workspaces/{workspace}/projects")).json()["items"]) == 1
    assert (await client.patch(f'/api/v1/projects/{project["id"]}', json={"expected_revision": 1, "name": "No"}, headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/workspaces/{workspace}/projects", json=INPUT, headers=headers)).status_code == 403
    async with tenant_session(data["app"].state.auth[1], actor_id=UUID(user["id"]), workspace_id=UUID(workspace)) as session:
        assert await session.scalar(text("SELECT count(*) FROM app.collections")) == 0
    async with owner.begin() as connection:
        await connection.execute(text("DELETE FROM app.memberships WHERE workspace_id=:w AND user_id=:u"), {"w": UUID(workspace), "u": UUID(user["id"])})
    assert (await client.get(f'/api/v1/projects/{project["id"]}')).status_code == 404
    assert (await client.get(f"/api/v1/workspaces/{workspace}/projects")).status_code == 404


async def test_pagination_is_bound_to_actor_workspace_and_resource(projects):
    client, _, owner, _, headers, workspace = projects
    created = [(await create(projects, {**INPUT, "name": str(i)}))["project"] for i in range(3)]
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.projects SET created_at='2026-01-01T00:00:00Z' WHERE workspace_id=:w"), {"w": UUID(workspace)})
    path = f"/api/v1/workspaces/{workspace}/projects"
    first = (await client.get(path, params={"limit": 2})).json()
    assert [p["id"] for p in first["items"]] == sorted(p["id"] for p in created)[:2]
    cursor = first["next_cursor"]
    last = (await client.get(path, params={"cursor": cursor})).json()
    assert [p["id"] for p in last["items"]] == sorted(p["id"] for p in created)[2:] and last["next_cursor"] is None
    other = (await client.post("/api/v1/workspaces", json={"name": "Other"}, headers=headers)).json()["id"]
    for endpoint, value in [(path, "x" + cursor[1:]), (f"/api/v1/workspaces/{other}/projects", cursor), ("/api/v1/workspaces", cursor)]:
        assert (await client.get(endpoint, params={"cursor": value})).status_code == 400
    for query in ("limit=0", "limit=101", "cursor=", "cursor=" + "x" * 2049):
        assert (await client.get(path + "?" + query)).status_code == 422


async def test_concurrent_edits_have_one_winner(projects):
    project = (await create(projects))["project"]
    responses = await asyncio.gather(*(projects[0].patch(f'/api/v1/projects/{project["id"]}',
        json={"expected_revision": 1, "goal": value}, headers=projects[4]) for value in ("First", "Second")))
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert (await projects[0].get(f'/api/v1/projects/{project["id"]}')).json() == winner


async def test_mutations_require_csrf_and_session(projects):
    project = (await create(projects))["project"]
    client, _, _, _, headers, workspace = projects
    for method, path, body in [("POST", f"/api/v1/workspaces/{workspace}/projects", INPUT),
        ("PATCH", f'/api/v1/projects/{project["id"]}', {"expected_revision": 1, "goal": "Changed"})]:
        for invalid in ({}, {**headers, "Origin": "https://evil.test"}, {**headers, "X-CSRF-Token": "wrong"}):
            assert (await client.request(method, path, json=body, headers=invalid)).status_code == 403
        cookie = dict(client.cookies)
        client.cookies.clear()
        assert (await client.request(method, path, json=body, headers=headers)).status_code == 401
        client.cookies.update(cookie)


@pytest.mark.parametrize("operation", ["create", "patch"])
async def test_owner_authority_is_rechecked_after_workspace_lock_wait(projects, operation):
    client, data, owner, user, headers, workspace = projects
    project = (await create(projects))["project"]
    task = None
    try:
        async with owner.begin() as lock:
            await lock.execute(text("SELECT id FROM app.workspaces WHERE id=:w FOR UPDATE"), {"w": UUID(workspace)})
            request = client.post(f"/api/v1/workspaces/{workspace}/projects", json=INPUT, headers=headers) if operation == "create" else client.patch(
                f'/api/v1/projects/{project["id"]}', json={"expected_revision": 1, "goal": "Changed"}, headers=headers)
            task = asyncio.create_task(request)
            async with data["app"].state.auth[1].connect() as observer:
                await wait_for_lock(observer, f"{operation if operation == 'create' else 'update'}_project")
            await lock.execute(text("UPDATE app.memberships SET role='member' WHERE workspace_id=:w AND user_id=:u"), {"w": UUID(workspace), "u": UUID(user["id"])})
        assert (await task).status_code == 403
        assert (await client.get(f'/api/v1/projects/{project["id"]}')).json() == project
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_private_function_failure_rolls_back_whole_creation(projects):
    from docweave.db.sessions import tenant_session

    _, data, owner, user, _, workspace = projects
    dependency = {"id": str(uuid4()), "technology": "FastAPI", "declared_version": None, "resolved_version": None, "docs_target": None}
    body = {**INPUT, "stack": [dependency, dependency]}
    with pytest.raises(DBAPIError):
        async with tenant_session(data["app"].state.auth[1], actor_id=UUID(user["id"]), workspace_id=UUID(workspace)) as session:
            await session.execute(text("SELECT app.create_project(CAST(:body AS jsonb))"), {"body": json.dumps(body)})
    async with owner.connect() as connection:
        for table in ("projects", "collections", "documentation_requests"):
            assert await connection.scalar(text(f"SELECT count(*) FROM app.{table} WHERE workspace_id=:w"), {"w": UUID(workspace)}) == 0


async def test_runtime_grants_and_collection_isolation(projects):
    from docweave.db.sessions import tenant_session

    _, data, _, user, _, workspace = projects
    project = (await create(projects))["project"]
    runtime = data["app"].state.auth[1]
    async with tenant_session(runtime, actor_id=UUID(user["id"]), workspace_id=UUID(workspace)) as session:
        assert await session.scalar(text("SELECT id FROM app.collections")) == UUID(project["default_collection_id"])
        assert await session.scalar(text("SELECT app.project_workspace(:p)"), {"p": PB}) is None
        assert await session.scalar(text("SELECT app.project_view(:p)"), {"p": PB}) is None
    for statement in ["SELECT * FROM app.documentation_requests", "DELETE FROM app.collections", "UPDATE app.projects SET name='No'",
        "SELECT app.replace_project_documentation(gen_random_uuid())"]:
        with pytest.raises(DBAPIError) as error:
            async with tenant_session(runtime, actor_id=UUID(user["id"]), workspace_id=UUID(workspace)) as session:
                await session.execute(text(statement))
        assert error.value.orig.sqlstate == "42501"


async def test_runtime_input_schema_matches_null_and_one_stack_validation(projects):
    schema = (await projects[0].get("/openapi.json")).json()
    for path, method, invalid in [
        ("/api/v1/workspaces/{workspace_id}/projects", "post", [
            {"name": "N", "goal": "G"}, {**INPUT, "stack_review_id": str(uuid4())},
            {**INPUT, "stack": None}, {**INPUT, "architecture_notes": None},
            {**INPUT, "stack": [{"technology": "FastAPI", "docs_target": None}]}]),
        ("/api/v1/projects/{project_id}", "patch", [{"expected_revision": 1}, {"expected_revision": 1, "goal": None}]),
    ]:
        body_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
        validator = Draft202012Validator({**body_schema, "components": schema["components"]}, format_checker=FormatChecker())
        for body in invalid:
            assert not validator.is_valid(body), body
    assert validator.is_valid({"expected_revision": 1, "architecture_notes": ""})


async def test_project_migration_backfills_existing_context_without_modifying_it(databases, test_urls):
    owner, _ = databases
    async with owner.connect() as connection:
        before = (await connection.execute(text("SELECT id,name,goal,stack,context_revision FROM app.projects ORDER BY id"))).all()
    await migrate(test_urls[1], "0004_memberships", downgrade=True)
    await migrate(test_urls[1], "head")
    async with owner.connect() as connection:
        assert (await connection.execute(text("SELECT id,name,goal,stack,context_revision FROM app.projects ORDER BY id"))).all() == before
        assert await connection.scalar(text("SELECT count(*) FROM app.collections WHERE is_default")) == len(before)
        assert await connection.scalar(text("SELECT count(*) FROM app.documentation_requests")) == 0


async def test_project_functions_have_fixed_search_path_and_private_helper(projects):
    async with projects[2].connect() as connection:
        rows = (await connection.execute(text("""
            SELECT p.proname,p.prosecdef,p.proconfig,has_function_privilege('docweave_runtime',p.oid,'EXECUTE') AS runtime,
                NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                    WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS no_public
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='app'
                AND p.proname IN ('project_workspace','project_view','replace_project_documentation','create_project','update_project')
        """))).all()
        assert len(rows) == 5
        assert all(r.prosecdef and r.no_public and r.proconfig == ["search_path=pg_catalog, app"] for r in rows)
        assert all(r.runtime == (r.proname != "replace_project_documentation") for r in rows)


@pytest.mark.parametrize("table", ["collections", "documentation_requests"])
async def test_child_records_cannot_reference_a_project_from_another_workspace(projects, table):
    from sqlalchemy.exc import IntegrityError

    project = (await create(projects))["project"]
    columns = "name,is_default" if table == "collections" else "requested_by,context_revision,state,reason"
    values = "'Invalid',false" if table == "collections" else ":user,1,'pending_review','version_unresolved'"
    with pytest.raises(IntegrityError) as error:
        async with projects[2].begin() as connection:
            await connection.execute(text(f"INSERT INTO app.{table}(workspace_id,project_id,{columns}) VALUES (:w,:p,{values})"),
                {"w": WB, "p": UUID(project["id"]), "user": UUID(projects[3]["id"])})
    assert error.value.orig.sqlstate == "23503"


async def test_migration_stops_before_changing_legacy_nonempty_stacks(databases, test_urls):
    owner, _ = databases
    await migrate(test_urls[1], "0004_memberships", downgrade=True)
    try:
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.projects SET stack='[\"FastAPI\"]'::jsonb WHERE id=:p"), {"p": PB})
        with pytest.raises(DBAPIError) as error:
            await migrate(test_urls[1], "head")
        assert error.value.orig.sqlstate == "22023"
        async with owner.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM app.alembic_version")) == "0004_memberships"
            assert await connection.scalar(text("SELECT to_regclass('app.collections')")) is None
            assert await connection.scalar(text("SELECT stack FROM app.projects WHERE id=:p"), {"p": PB}) == ["FastAPI"]
    finally:
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.projects SET stack='[]'::jsonb WHERE id=:p"), {"p": PB})
        await migrate(test_urls[1], "head")


async def test_patch_pending_request_failure_rolls_back_context_and_requests(projects, monkeypatch):
    project = (await create(projects))["project"]
    monkeypatch.setattr("docweave.services.projects.uuid4", lambda: UUID(project["stack"][0]["id"]))
    path = f'/api/v1/projects/{project["id"]}'
    response = await projects[0].patch(path, json={"expected_revision": 1, "goal": "Must roll back",
        "stack": [{"technology": "Python"}]}, headers=projects[4])
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "Must roll back" not in response.text
    assert (await projects[0].get(path)).json() == project
    async with projects[2].connect() as connection:
        rows = (await connection.execute(text("SELECT id,state,context_revision FROM app.documentation_requests WHERE project_id=:p"),
            {"p": UUID(project["id"])})).all()
        assert {str(r.id) for r in rows} == {dep["id"] for dep in project["stack"]}
        assert all(r.state == "pending_review" and r.context_revision == 1 for r in rows)
