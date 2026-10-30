"""Credential repair is checked only against the explicitly guarded disposable service."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from psycopg import sql
from sqlalchemy import text

from test_database import checked_test_urls, databases, test_urls  # noqa: F401


@pytest.mark.anyio
async def test_login_repair_preserves_rows_and_restricted_roles(databases, test_urls):
    from docweave.db import make_engine
    from docweave.settings import database_url
    owner, runtime = databases
    worker_url = database_url("TEST_WORKER_DATABASE_URL")
    checked_test_urls(worker_url.render_as_string(hide_password=False), test_urls[1].render_as_string(hide_password=False))
    script = (Path(__file__).resolve().parents[1] / "infra" / "postgres" / "repair-development-logins.sql").read_text()
    for name, password in (("migration", test_urls[1].password), ("runtime", test_urls[0].password), ("worker", worker_url.password)):
        script = script.replace(":" + "'" + name + "_password'", sql.Literal(password).as_string())
    async with owner.connect() as connection:
        before = await connection.scalar(text("SELECT count(*) FROM app.projects"))
    process = await asyncio.to_thread(subprocess.run, ["docker", "compose", "exec", "-T", "test-db", "psql", "-X", "-q",
        "-U", "docweave_admin", "-d", "docweave_test"], input=script.encode(), capture_output=True, timeout=15)
    assert process.returncode == 0, "Disposable credential repair failed; private SQL output withheld."
    worker = make_engine(worker_url)
    try:
        for engine in (owner, runtime, worker):
            async with engine.connect() as connection:
                flags = (await connection.execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"))).one()
                assert tuple(flags) == (False, False)
        async with owner.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM app.projects")) == before
            assert await connection.scalar(text("SELECT n.nspowner::regrole::text FROM pg_namespace n WHERE n.nspname='queue'")) == "docweave_migrator"
    finally:
        await worker.dispose()
