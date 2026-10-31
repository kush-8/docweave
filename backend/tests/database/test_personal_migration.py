"""Additive personal ownership migration; guarded disposable database only."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.database.test_database import A, B, C, PA, PB, WA, WB
from tests.database.test_database import databases, migrate, test_urls  # noqa: F401


COLUMNS = {'owner_user_id', 'repository_id', 'repository_branch', 'application_path',
           'last_commit_sha', 'stack_fingerprint', 'sync_status'}


def test_personal_project_model_keeps_legacy_scope_and_nullable_owner():
    from docweave.db.models import Project

    assert COLUMNS <= set(Project.__table__.columns.keys())
    assert Project.__table__.c.owner_user_id.nullable
    assert 'workspace_id' in Project.__table__.c
    assert Project.__table__.c.repository_id.type.python_type is int


@pytest.mark.anyio
async def test_sole_owner_backfill_preserves_records_and_ambiguous_owner_is_unassigned(databases, test_urls):
    owner, runtime = databases
    await migrate(test_urls[1], '0012_public_pilot_budget', downgrade=True)
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (:workspace,:actor,'owner')"), {'workspace': WB, 'actor': C})
        before_projects = (await connection.execute(text('SELECT id,workspace_id,name,goal,stack,context_revision,created_at FROM app.projects ORDER BY id'))).all()
        before_collections = (await connection.execute(text('SELECT id,project_id,workspace_id,name,created_at FROM app.collections ORDER BY id'))).all()
    await migrate(test_urls[1], 'head')
    try:
        async with owner.connect() as connection:
            assert (await connection.execute(text('SELECT id,workspace_id,name,goal,stack,context_revision,created_at FROM app.projects ORDER BY id'))).all() == before_projects
            assert (await connection.execute(text('SELECT id,project_id,workspace_id,name,created_at FROM app.collections ORDER BY id'))).all() == before_collections
            rows = dict((await connection.execute(text('SELECT id,owner_user_id FROM app.projects'))).all())
            assert rows == {PA: A, PB: None}
        async with runtime.begin() as connection:
            await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor': str(A)})
            assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PA}) is True
            assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PB}) is False
            await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor': str(B)})
            assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PA}) is False
            assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PB}) is False
        # Only an explicit privileged mapping grants the previously ambiguous project.
        async with owner.begin() as connection:
            await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:project'), {'actor': B, 'project': PB})
        async with runtime.begin() as connection:
            await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor': str(B)})
            assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PB}) is True
    finally:
        # Leave the shared disposable target on head even if an assertion fails.
        await migrate(test_urls[1], 'head')


@pytest.mark.anyio
async def test_new_owner_helper_is_private_and_does_not_replace_legacy_policy(databases):
    owner, runtime = databases
    async with owner.connect() as connection:
        row = (await connection.execute(text("SELECT p.prosecdef,p.proconfig,coalesce(bool_or(a.grantee=0 AND a.privilege_type='EXECUTE'),false) AS public_execute FROM pg_proc p LEFT JOIN LATERAL aclexplode(p.proacl) a ON true WHERE p.oid='app.personal_project_owned(uuid)'::regprocedure GROUP BY p.oid,p.prosecdef,p.proconfig"))).one()
        assert row.prosecdef is True
        assert row.proconfig == ['search_path=pg_catalog, app']
        assert row.public_execute is False
        policies = (await connection.execute(text("SELECT policyname FROM pg_policies WHERE schemaname='app' AND tablename='projects'"))).scalars().all()
        assert set(policies) == {'runtime_read', 'personal_owner_read'}
    async with runtime.begin() as connection:
        assert await connection.scalar(text('SELECT app.personal_project_owned(:project)'), {'project': PA}) is False
    with pytest.raises(DBAPIError):
        async with runtime.begin() as connection:
            await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:project'), {'actor': C, 'project': PA})
