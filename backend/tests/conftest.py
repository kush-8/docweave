import pytest
from httpx import ASGITransport
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def isolated_deletion_journal(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp('deletion-journal')
    monkeypatch.setenv('DELETION_JOURNAL_ROOT', str(root))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app():
    from docweave.main import create_app

    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield client
