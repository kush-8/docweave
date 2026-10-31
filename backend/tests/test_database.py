"""Integration tests use only the explicitly configured disposable database."""

import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import make_url
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[2]
A = UUID("00000000-0000-4000-8000-000000000001")
B = UUID("00000000-0000-4000-8000-000000000002")
C = UUID("00000000-0000-4000-8000-000000000003")
WA = UUID("10000000-0000-4000-8000-000000000001")
WB = UUID("10000000-0000-4000-8000-000000000002")
PA = UUID("20000000-0000-4000-8000-000000000001")
PB = UUID("20000000-0000-4000-8000-000000000002")
TABLES = ("users", "workspaces", "memberships", "projects")


def checked_test_urls(runtime, migration, development=None):
    if not runtime or not migration:
        raise ValueError("TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL are required")
    urls = [make_url(value) for value in (runtime, migration)]
    targets = [(url.host, url.port, url.database) for url in urls]
    if any(url.query for url in urls):
        raise ValueError("Test connection URLs cannot contain query parameters")
    if any(url.drivername != "postgresql+asyncpg" or url.database != "docweave_test" for url in urls):
        raise ValueError("Database tests require postgresql+asyncpg and docweave_test")
    if any(target != ("127.0.0.1", 55433, "docweave_test") for target in targets):
        raise ValueError("Database tests require the isolated local test service on port 55433")
    if targets[0] != targets[1] or urls[0].username == urls[1].username:
        raise ValueError("Test roles must be distinct logins on the same test database")
    if development:
        dev = make_url(development)
        if dev.query:
            raise ValueError("Cannot safely compare a development URL containing query parameters")
        if (dev.host, dev.port, dev.database) == targets[0]:
            raise ValueError("Database tests cannot target the development database")
    return urls


@pytest.mark.parametrize(("runtime", "migration", "development"), [
    (None, None, None),
    ("postgresql+asyncpg://reader@localhost/docweave", "postgresql+asyncpg://owner@localhost/docweave", None),
    ("postgresql+asyncpg://same@localhost/docweave_test", "postgresql+asyncpg://same@localhost/docweave_test", None),
    ("postgresql+asyncpg://reader@localhost:55433/docweave_test", "postgresql+asyncpg://owner@localhost:55432/docweave_test", None),
    ("sqlite:///docweave_test", "sqlite:///docweave_test", None),
    ("postgresql+asyncpg://reader@localhost/docweave_test", "postgresql+asyncpg://owner@localhost/docweave_test", "postgresql+asyncpg://app@localhost/docweave_test"),
])
def test_database_test_guard_refuses_unsafe_targets(runtime, migration, development):
    with pytest.raises(ValueError):
        checked_test_urls(runtime, migration, development)


@pytest.mark.parametrize("query", ["port=55432&database=docweave", "host=other-server", "database=docweave"])
def test_database_test_guard_rejects_query_target_overrides(query):
    runtime = f"postgresql+asyncpg://docweave_runtime:test@127.0.0.1:55433/docweave_test?{query}"
    migration = f"postgresql+asyncpg://docweave_migrator:test@127.0.0.1:55433/docweave_test?{query}"
    with pytest.raises(ValueError):
        checked_test_urls(runtime, migration,
                          "postgresql+asyncpg://docweave_runtime:test@127.0.0.1:55432/docweave")


@pytest.mark.parametrize("host_port", ["127.0.0.1:55432", "other-server:55433"])
def test_database_test_guard_rejects_unapproved_endpoint(host_port):
    runtime = f"postgresql+asyncpg://docweave_runtime:test@{host_port}/docweave_test"
    migration = f"postgresql+asyncpg://docweave_migrator:test@{host_port}/docweave_test"
    with pytest.raises(ValueError):
        checked_test_urls(runtime, migration)


def test_database_test_guard_accepts_only_the_approved_local_pair():
    urls = checked_test_urls(
        "postgresql+asyncpg://docweave_runtime:test@127.0.0.1:55433/docweave_test",
        "postgresql+asyncpg://docweave_migrator:test@127.0.0.1:55433/docweave_test",
        "postgresql+asyncpg://docweave_runtime:test@127.0.0.1:55432/docweave",
    )
    assert [url.database for url in urls] == ["docweave_test", "docweave_test"]


def test_database_configuration_requires_an_explicit_url(monkeypatch):
    from docweave.core.settings import database_url

    monkeypatch.delenv("MISSING_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="MISSING_DATABASE_URL"):
        database_url("MISSING_DATABASE_URL")


@pytest.mark.parametrize("value", ["sqlite:///data.db", "not-a-url", "postgresql+asyncpg://user@localhost"])
def test_database_configuration_rejects_invalid_urls_without_exposing_them(monkeypatch, value):
    from docweave.core.settings import database_url

    monkeypatch.setenv("TEST_INVALID_URL", value)
    with pytest.raises(ValueError) as error:
        database_url("TEST_INVALID_URL")
    assert value not in str(error.value)


def test_database_configuration_does_not_export_administrator_credentials(monkeypatch):
    from docweave.core.settings import database_url

    monkeypatch.delenv("PG_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("CONFIGURED_RUNTIME_URL", "postgresql+asyncpg://reader:example@127.0.0.1:55432/docweave")
    database_url("CONFIGURED_RUNTIME_URL")
    administrator_was_exported = "PG_ADMIN_PASSWORD" in os.environ
    assert administrator_was_exported is False


@pytest.fixture
def test_urls():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    return checked_test_urls(values.get("TEST_DATABASE_URL"), values.get("TEST_MIGRATION_DATABASE_URL"),
                             values.get("DATABASE_URL"))


async def migrate(url, revision, *, downgrade=False):
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            def run(sync_connection):
                config = Config(str(ROOT / "backend" / "alembic.ini"))
                config.attributes["connection"] = sync_connection
                (command.downgrade if downgrade else command.upgrade)(config, revision)
            await connection.run_sync(run)
    finally:
        await engine.dispose()


@pytest.fixture
async def databases(test_urls):
    from docweave.db.engine import make_engine

    runtime_url, migration_url = test_urls
    await migrate(migration_url, "head")
    owner = make_engine(migration_url)
    runtime = make_engine(runtime_url)
    try:
        async with owner.begin() as connection:
            # Versioned profiles are immutable; this guarded disposable reset names every dependent table.
            await connection.execute(text("TRUNCATE app.compatibility_operations,app.compatibility_requests,app.cost_reservations,app.provider_profiles"))
            await connection.execute(text("DELETE FROM app.workspace_allowances"))
            await connection.execute(text("TRUNCATE app.chunks,app.document_indexes,app.index_generations,app.ingestion_jobs,app.document_versions,app.documents,app.sources,app.documentation_selections"))
            await connection.execute(text("TRUNCATE queue.procrastinate_jobs,queue.procrastinate_events,queue.procrastinate_workers RESTART IDENTITY CASCADE"))
            for table in ("auth_sessions", "auth_flows", "auth_rate_limits"):
                await connection.execute(text(f"DELETE FROM app.{table}"))
            for table in ("collection_processor_approvals", "project_processor_approvals", "collection_grants", "documentation_requests", "collections", "invitations", "projects", "memberships", "workspaces", "users"):
                await connection.execute(text(f"DELETE FROM app.{table}"))
            await connection.execute(text("UPDATE app.processors SET enabled=false"))
            for actor, subject in [(A, "actor-a"), (B, "actor-b"), (C, "no-membership")]:
                await connection.execute(text("INSERT INTO app.users (id,issuer,subject,display_name,email) VALUES (:id,'https://issuer.test',:subject,:subject,'shared@example.test')"), {"id": actor, "subject": subject})
            for workspace, actor, project, name in [(WA, A, PA, "Alpha"), (WB, B, PB, "Beta")]:
                await connection.execute(text("INSERT INTO app.workspaces (id,name) VALUES (:id,:name)"), {"id": workspace, "name": name})
                await connection.execute(text("INSERT INTO app.memberships (workspace_id,user_id,role) VALUES (:workspace,:actor,'owner')"), {"workspace": workspace, "actor": actor})
                await connection.execute(text("INSERT INTO app.projects (id,workspace_id,name,goal) VALUES (:id,:workspace,:name,'Learn retrieval')"), {"id": project, "workspace": workspace, "name": name})
                await connection.execute(text("INSERT INTO app.collections(project_id,workspace_id,name,is_default) VALUES (:p,:w,'Default',true)"), {"p": project, "w": workspace})
        yield owner, runtime
    finally:
        await owner.dispose()
        await runtime.dispose()


@pytest.mark.anyio
async def test_postgres_vector_and_restricted_role_are_available(databases):
    _, runtime = databases
    async with runtime.connect() as connection:
        assert (await connection.scalar(text("SELECT current_user"))) == "docweave_runtime"
        assert (await connection.scalar(text("SELECT '[1,2]'::vector <-> '[1,2]'::vector"))) == 0
        role = (await connection.execute(text("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"))).one()
        assert tuple(role) == (False, False, False, False)


@pytest.mark.anyio
async def test_migration_upgrade_is_repeatable(databases, test_urls):
    await migrate(test_urls[1], "head")
    owner, _ = databases
    async with owner.connect() as connection:
        assert (await connection.scalar(text("SELECT count(*) FROM app.projects"))) == 2
        assert (await connection.scalar(text("SELECT count(*) FROM app.alembic_version"))) == 1


@pytest.mark.anyio
async def test_migration_downgrade_then_upgrade_recreates_empty_tables(test_urls):
    await migrate(test_urls[1], "head")
    await migrate(test_urls[1], "base", downgrade=True)
    engine = create_async_engine(test_urls[1])
    try:
        async with engine.connect() as connection:
            assert (await connection.scalar(text("SELECT to_regclass('app.projects')"))) is None
        await migrate(test_urls[1], "head")
        async with engine.connect() as connection:
            assert (await connection.scalar(text("SELECT count(*) FROM app.projects"))) == 0
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_models_persist_defaults_and_same_email_does_not_merge_identity(databases):
    from sqlalchemy.ext.asyncio import AsyncSession
    from docweave.db.models import Project
    from docweave.db.models import User

    owner, _ = databases
    async with AsyncSession(owner) as session, session.begin():
        session.add(User(issuer="https://other-issuer.test", subject="actor-a", display_name="Other identity", email="shared@example.test"))
        project = Project(workspace_id=WA, name="New project", goal="Explain citations")
        session.add(project)
        await session.flush()
        project_id = project.id
    async with AsyncSession(owner) as session:
        saved = await session.get(Project, project_id)
        assert saved.context_revision == 1
        assert saved.stack == []
        assert saved.created_at.utcoffset().total_seconds() == 0
        assert len((await session.scalars(select(User))).all()) == 4


@pytest.mark.anyio
async def test_failed_transaction_does_not_persist_partial_writes(databases):
    owner, _ = databases
    with pytest.raises(IntegrityError):
        async with owner.begin() as connection:
            await connection.execute(text("INSERT INTO app.workspaces(name) VALUES ('Must roll back')"))
            await connection.execute(text("INSERT INTO app.projects(workspace_id,name,goal) VALUES (:workspace,'','invalid')"), {"workspace": WA})
    async with owner.connect() as connection:
        assert (await connection.scalar(text("SELECT count(*) FROM app.workspaces WHERE name='Must roll back'"))) == 0


@pytest.mark.parametrize(("statement", "constraint"), [
    ("INSERT INTO app.users(issuer,subject,display_name) VALUES ('https://issuer.test','actor-a','Duplicate')", "uq_users_issuer_subject"),
    ("INSERT INTO app.users(issuer,subject) VALUES ('https://issuer.test','missing-name')", "display_name"),
    ("INSERT INTO app.users(issuer,subject,display_name) VALUES ('https://issuer.test','blank-name',' ')", "ck_users_nonblank_display_name"),
    ("INSERT INTO app.workspaces(name) VALUES (E' \\t\\n')", "ck_workspaces_nonblank_name"),
    ("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:workspace,:actor,'owner')", "pk_memberships"),
    ("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:workspace,:other,'admin')", "ck_memberships_valid_role"),
    ("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:other,:actor,'member')", "fk_memberships_workspace_id_workspaces"),
    ("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:workspace,:missing,'member')", "fk_memberships_user_id_users"),
    ("INSERT INTO app.projects(workspace_id,name,goal) VALUES (:missing,'New','Goal')", "fk_projects_workspace_id_workspaces"),
    ("INSERT INTO app.projects(workspace_id,name,goal) VALUES (:workspace,'New',' ')", "ck_projects_nonblank_goal"),
    ("INSERT INTO app.projects(workspace_id,name,goal,context_revision) VALUES (:workspace,'New','Goal',0)", "ck_projects_positive_context_revision"),
    ("INSERT INTO app.projects(workspace_id,name,goal,stack) VALUES (:workspace,'New','Goal','{}')", "ck_projects_stack_array"),
    ("DELETE FROM app.workspaces WHERE id=:workspace", "fk_memberships_workspace_id_workspaces"),
])
@pytest.mark.anyio
async def test_database_constraints_reject_invalid_rows(databases, statement, constraint):
    owner, _ = databases
    with pytest.raises(IntegrityError) as error:
        async with owner.begin() as connection:
            await connection.execute(text(statement), {"workspace": WA, "actor": A, "other": B, "missing": UUID(int=99)})
    assert constraint in str(error.value.orig)


@pytest.mark.anyio
async def test_tenant_context_limits_each_table_to_authorized_rows(databases):
    from docweave.db.sessions import tenant_session

    _, runtime = databases
    async with tenant_session(runtime, actor_id=A, workspace_id=WA) as session:
        for table in TABLES:
            assert (await session.scalar(text(f"SELECT count(*) FROM app.{table}"))) == 1
        assert (await session.scalar(text("SELECT id FROM app.projects WHERE id=:id"), {"id": PB})) is None
        assert (await session.scalar(text("SELECT id FROM app.users WHERE id=:id"), {"id": B})) is None
    async with tenant_session(runtime, actor_id=B, workspace_id=WB) as session:
        assert (await session.scalar(text("SELECT id FROM app.projects"))) == PB


@pytest.mark.parametrize(("actor", "workspace"), [(A, WB), (B, WA), (C, WA)])
@pytest.mark.anyio
async def test_tenant_context_cannot_replace_membership(databases, actor, workspace):
    from docweave.db.sessions import tenant_session

    _, runtime = databases
    async with tenant_session(runtime, actor_id=actor, workspace_id=workspace) as session:
        for table in TABLES:
            expected = 1 if table == "users" else 0
            assert (await session.scalar(text(f"SELECT count(*) FROM app.{table}"))) == expected


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.anyio
async def test_pool_reuse_clears_context_after_commit_and_rollback(databases, rollback):
    from docweave.db.sessions import tenant_session

    _, runtime = databases
    try:
        async with tenant_session(runtime, actor_id=A, workspace_id=WA) as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert (await session.scalar(text("SELECT count(*) FROM app.projects"))) == 1
            if rollback:
                raise RuntimeError("Abort transaction")
    except RuntimeError:
        assert rollback
    async with runtime.connect() as connection:
        assert (await connection.scalar(text("SELECT pg_backend_pid()"))) == pid
        for table in TABLES:
            assert (await connection.scalar(text(f"SELECT count(*) FROM app.{table}"))) == 0
        assert not (await connection.scalar(text("SELECT current_setting('docweave.actor_id',true)")))
        assert not (await connection.scalar(text("SELECT current_setting('docweave.workspace_id',true)")))


@pytest.mark.parametrize("statement", [
    "INSERT INTO app.workspaces(name) VALUES ('Forbidden')",
    "UPDATE app.projects SET name='Forbidden'",
    "DELETE FROM app.memberships",
    "TRUNCATE app.projects",
    "CREATE TABLE app.forbidden(id integer)",
    "CREATE TABLE public.forbidden(id integer)",
    "CREATE SCHEMA forbidden",
    "ALTER TABLE app.projects DISABLE ROW LEVEL SECURITY",
    "SET ROLE docweave_migrator",
])
@pytest.mark.anyio
async def test_runtime_cannot_write_change_schema_or_assume_owner(databases, statement):
    from docweave.db.sessions import tenant_session

    _, runtime = databases
    with pytest.raises(DBAPIError) as error:
        async with tenant_session(runtime, actor_id=A, workspace_id=WA) as session:
            await session.execute(text(statement))
    assert error.value.orig.sqlstate == "42501"


@pytest.mark.anyio
async def test_runtime_cannot_disable_row_security_to_read_other_tenants(databases):
    _, runtime = databases
    with pytest.raises(DBAPIError) as error:
        async with runtime.begin() as connection:
            await connection.execute(text("SET LOCAL row_security=off"))
            await connection.execute(text("SELECT * FROM app.projects"))
    assert error.value.orig.sqlstate == "42501"
