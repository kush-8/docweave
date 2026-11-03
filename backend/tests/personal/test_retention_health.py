from contextlib import asynccontextmanager
import json
import time

import pytest
from sqlalchemy import make_url
from docweave.services import retention

pytestmark = pytest.mark.anyio


@pytest.fixture
def engine(monkeypatch):
    class Engine:
        url = make_url('postgresql+asyncpg://runtime:fixture@127.0.0.1:55433/docweave_test')
        @asynccontextmanager
        async def connect(self):
            yield None
    async def clear(connection):
        return False
    monkeypatch.setattr(retention.repository, 'overdue', clear)
    return Engine()


async def test_missing_failed_stale_and_corrupt_health_never_allow_traffic(engine):
    with pytest.raises(OSError):
        await retention.assert_current(engine)
    retention.mark(engine, False)
    with pytest.raises(ValueError):
        await retention.assert_current(engine)
    retention.mark(engine, True)
    await retention.assert_current(engine)
    with pytest.raises(ValueError):
        await retention.assert_current(engine, since=time.monotonic()+1)
    path = retention.health_path(engine)
    state = json.loads(path.read_text())
    for completed in (time.monotonic()-31, float('nan'), time.monotonic()+100):
        path.write_text(json.dumps({**state, 'completed': completed}))
        with pytest.raises(ValueError):
            await retention.assert_current(engine)
    path.write_text('x'*4097)
    with pytest.raises(ValueError, match='Oversized'):
        await retention.assert_current(engine)


async def test_health_cannot_be_reused_by_another_database_or_storage_root(engine, tmp_path):
    retention.mark(engine, True, artifact_root=tmp_path / 'one')
    await retention.assert_current(engine, artifact_root=tmp_path / 'one')
    with pytest.raises(OSError):
        await retention.assert_current(engine, artifact_root=tmp_path / 'two')
    engine.url = engine.url.set(database='other_isolated_database')
    with pytest.raises(OSError):
        await retention.assert_current(engine, artifact_root=tmp_path / 'one')
