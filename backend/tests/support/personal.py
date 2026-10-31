"""Current GitHub application with two users and an API-created personal project."""
import asyncio
import json
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4
import httpx
import pytest
from sqlalchemy import text
from tests.github.test_github import github_login
from tests.database.test_database import databases, test_urls, PA, WA


@pytest.fixture
async def collections(github_login):
    from docweave.main import create_app
    from docweave.services.github_auth import begin_login, complete_login
    settings, runtime, owner, github, state, cookie, _, _ = github_login
    async def user(token):
        identity = 13 if token == 'guest-token' else 12
        return {'id': identity, 'login': str(identity), 'name': str(identity)}
    async def exchange(*args):
        return {'access_token': 'guest-token'}
    async def repository(*args):
        return {'id': 42, 'name': 'repo', 'full_name': 'owner/repo', 'default_branch': 'main'}
    async def head(*args):
        return "a" * 40
    github.user, github.exchange_code, github.repository, github.head = user, exchange, repository, head
    url, browser = await begin_login(settings, runtime, github, '127.0.0.1', '')
    guest_cookie, _ = await complete_login(settings, runtime, github,
        {'state': parse_qs(urlsplit(url).query)['state'][0], 'code': 'guest'}, browser, '')
    app = create_app(github_settings=settings, auth_engine=runtime, github_client=github)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url=settings.origin) as admin, httpx.AsyncClient(transport=transport, base_url=settings.origin) as guest:
        admin.cookies.set('docweave_session', cookie)
        guest.cookies.set('docweave_session', guest_cookie)
        current, recipient = (await admin.get('/api/v1/me')).json(), (await guest.get('/api/v1/me')).json()
        headers = {'Origin': settings.origin, 'X-CSRF-Token': current['csrf_token']}
        response = await admin.post('/api/v1/projects', json={'repository_id': 42, 'goal': 'Cited support'}, headers=headers)
        assert response.status_code == 201, response.text
        project = response.json()
        async with owner.connect() as connection:
            assert await connection.scalar(text('SELECT workspace_id FROM app.projects WHERE id=:id'), {'id': UUID(project['id'])}) is None
        stack = [{'id': str(uuid4()), 'technology': 'FastAPI', 'docs_target': None}]
        async with owner.begin() as connection:
            await connection.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:project'),
                {'project': UUID(project['id']), 'stack': json.dumps(stack)})
        yield {'admin': admin, 'guest': guest, 'owner': owner, 'runtime': runtime, 'user': current,
            'recipient': recipient, 'workspace': {'id': str(WA)}, 'project': project['id'], 'collection': project['default_collection_id'],
            'headers': {'Origin': settings.origin, 'X-CSRF-Token': current['csrf_token']},
            'guest_headers': {'Origin': settings.origin, 'X-CSRF-Token': recipient['csrf_token']}, 'data': {'app': app}}


def policy_path(c, kind):
    return f'/api/v1/{"projects" if kind == "project" else "collections"}/{c[kind]}/processing-policy'


async def configure_processors(c):
    async with c['owner'].begin() as connection:
        for identity, provider, backend, roles in (
            ('test:gemini:embedding:v1', 'gemini', 'test-google', '["embedding"]'),
            ('test:groq:generation:v1', 'groq', 'test-groq', '["generation"]')):
            await connection.execute(text('INSERT INTO app.processors(id,provider,backend,roles) VALUES(:id,:provider,:backend,CAST(:roles AS jsonb)) ON CONFLICT DO NOTHING'),
                {'id': identity, 'provider': provider, 'backend': backend, 'roles': roles})
            await connection.execute(text('UPDATE app.processors SET enabled=true WHERE id=:id'), {'id': identity})


async def wait_for_lock(observer, operation):
    for _ in range(100):
        await observer.execute(text('SELECT pg_stat_clear_snapshot()'))
        if await observer.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE usename='docweave_runtime' AND wait_event_type='Lock' AND query LIKE :operation)"), {'operation': '%app.'+operation+'%'}):
            return
        await asyncio.sleep(0.01)
    raise AssertionError('Request never reached the held lock')
