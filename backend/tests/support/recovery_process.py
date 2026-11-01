"""Real queue worker for kill/restart acceptance; all non-test-network IO is blocked."""
import asyncio
import os
from pathlib import Path
import socket

from docweave.core.settings import database_url
from docweave.integrations.stack import parse_stack
from tests.database.test_database import checked_test_urls

checked_test_urls(*(database_url(name).render_as_string(hide_password=False) for name in ('DATABASE_URL', 'WORKER_DATABASE_URL')))
original_connect = socket.socket.connect


def test_database_only(sock, address):
    if not isinstance(address, tuple) or address[:2] != ('127.0.0.1', 55433):
        raise AssertionError('Acceptance worker may connect only to the disposable database')
    return original_connect(sock, address)


loop = asyncio.SelectorEventLoop()
socket.socket.connect = test_database_only

from docweave.workers import personal  # noqa: E402
from docweave.services import personal_worker  # noqa: E402


class FixtureGitHub:
    async def user(self, token):
        return {'id': 12}

    async def repository(self, token, identity):
        return {'id': identity, 'name': 'fixture', 'default_branch': 'main'}


async def scan(*args, **kwargs):
    if os.environ['RECOVERY_TEST_MODE'] == 'pause':
        Path(os.environ['RECOVERY_TEST_SENTINEL']).write_text('leased-and-scanning', encoding='utf-8')
        await asyncio.Future()
    return {'commit_sha': 'a' * 40, 'scan': parse_stack({'package.json': b'{}'}), 'unchanged': False}


personal.GitHubClient = lambda settings: FixtureGitHub()
personal_worker.scan_repository = scan
asyncio.run(personal.run_worker(), loop_factory=lambda: loop)
