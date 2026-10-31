"""Direct-owner RPCs must never expose another user's private project."""
import pytest
from sqlalchemy import text
from tests.database.test_database import A, B, PA, databases, test_urls

pytestmark=pytest.mark.anyio

async def test_personal_project_creation_and_owner_isolation(databases):
    owner,runtime=databases
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor':str(A)})
        project=await connection.scalar(text("SELECT app.personal_create_project(CAST(:body AS jsonb))"), {'body':'{"name":"Repo","goal":"Help","repository_id":42,"branch":"main","application_path":""}'})
        assert project['repository']['repository_id']==42
        assert project['sync_state']=='pending'
        identity=project['id']
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor':str(B)})
        assert await connection.scalar(text('SELECT app.personal_project(CAST(:id AS uuid))'), {'id':identity}) is None
    async with owner.connect() as connection:
        assert await connection.scalar(text('SELECT workspace_id FROM app.projects WHERE id=CAST(:id AS uuid)'),{'id':identity}) is None

async def test_personal_legacy_project_requires_repo_setup(databases):
    owner,runtime=databases
    async with owner.begin() as connection:
        await connection.execute(text('UPDATE app.projects SET owner_user_id=:actor WHERE id=:p'), {'actor':A,'p':PA})
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor':str(A)})
        project=await connection.scalar(text('SELECT app.personal_project(:id)'), {'id':PA})
        assert project['repository'] is None
        assert project['sync_state']=='repository_required'


async def test_default_application_is_github_only_and_has_no_saas_routes():
    from docweave.main import create_app
    app=create_app()
    paths=set(app.openapi()['paths'])
    assert '/api/v1/projects' in paths and '/api/v1/catalog' in paths
    assert not any('/workspaces' in path or '/invitations' in path or '/grants' in path for path in paths)
    login=app.openapi()['paths']['/api/v1/auth/login']['get']
    assert not any(p['name']=='method' for p in login.get('parameters',[]))

async def test_conversation_and_turn_intent_are_durable_and_idempotent(databases):
    import json
    from uuid import uuid4
    owner,runtime=databases
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(A)})
        project=await connection.scalar(text('SELECT app.personal_create_project(CAST(:body AS jsonb))'),{'body':'{"name":"Repo","goal":"Help","repository_id":42,"branch":"main"}'})
        conversation=await connection.scalar(text('SELECT app.personal_create_conversation(CAST(:project AS uuid),NULL)'),{'project':project['id']})
        assert conversation['status']=='initializing'
        identity=conversation['id']
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.conversations SET status='ready' WHERE id=CAST(:id AS uuid)"),{'id':identity})
    key=uuid4()
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(A)})
        first=await connection.scalar(text('SELECT app.personal_append_turn(CAST(:id AS uuid),:key,:message)'),{'id':identity,'key':key,'message':'Help with React'})
        second=await connection.scalar(text('SELECT app.personal_append_turn(CAST(:id AS uuid),:key,:message)'),{'id':identity,'key':key,'message':'Help with React'})
        assert first['id']==second['id'] and first['status']=='queued'
    async with runtime.begin() as connection:
        await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"),{'actor':str(B)})
        assert await connection.scalar(text('SELECT app.personal_conversation(CAST(:id AS uuid))'),{'id':identity}) is None
