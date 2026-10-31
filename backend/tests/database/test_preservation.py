"""Read-only restored-copy comparisons include values, not just row counts."""
import asyncio
import subprocess

import pytest
from sqlalchemy import text

from docweave.repositories.ownership import preservation_snapshot
from tests.database.test_database import A, WA, PA, checked_test_urls, databases, test_urls  # noqa: F401
from tests.paths import REPO_ROOT


@pytest.mark.anyio
async def test_preservation_detects_value_changes_with_identical_counts(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        before = await preservation_snapshot(connection)
        await connection.execute(text("UPDATE app.projects SET goal='changed' WHERE id=:id"), {"id": PA})
        after = await preservation_snapshot(connection)
        assert before["app.projects"]["rows"] == after["app.projects"]["rows"]
        assert before["app.projects"]["sha256"] != after["app.projects"]["sha256"]


@pytest.mark.anyio
async def test_preservation_refuses_rls_filtered_runtime_snapshots(databases):
    _, runtime = databases
    async with runtime.begin() as connection:
        with pytest.raises(ValueError, match="migration role"):
            await preservation_snapshot(connection)


@pytest.mark.anyio
async def test_migration_comparison_projects_original_columns_and_rejects_missing_columns(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        before = await preservation_snapshot(connection)
    async with owner.begin() as connection:
        await connection.execute(text("ALTER TABLE app.projects ADD COLUMN rehearsal_marker text DEFAULT 'new'"))
    try:
        async with owner.begin() as connection:
            after = await preservation_snapshot(connection, baseline=before)
            assert after == before
            before["app.projects"]["columns"].append("missing_column")
            with pytest.raises(ValueError, match="columns"):
                await preservation_snapshot(connection, baseline=before)
    finally:
        async with owner.begin() as connection:
            await connection.execute(text("ALTER TABLE app.projects DROP COLUMN rehearsal_marker"))


def test_artifact_comparison_hashes_bytes_and_refuses_missing_roots(tmp_path):
    from docweave.storage.artifacts import snapshot_artifacts
    (tmp_path / "document").write_bytes(b"before")
    before = snapshot_artifacts(tmp_path)
    (tmp_path / "document").write_bytes(b"after!")
    assert snapshot_artifacts(tmp_path) != before
    with pytest.raises(ValueError):
        snapshot_artifacts(tmp_path / "missing")


@pytest.mark.anyio
async def test_operator_capture_compare_is_read_only_and_reports_drift(databases, tmp_path):
    from docweave import preservation
    owner, _ = databases
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "document").write_text("private content", encoding="utf-8")
    baseline = await preservation.capture(url_env="TEST_MIGRATION_DATABASE_URL", artifacts=artifacts)
    assert "private content" not in str(baseline)
    current = await preservation.capture(url_env="TEST_MIGRATION_DATABASE_URL", artifacts=artifacts, baseline=baseline)
    assert preservation.compare(baseline, current)["preserved"] is True
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.projects SET goal='drift' WHERE id=:id"), {"id": PA})
    (artifacts / "document").unlink()
    current = await preservation.capture(url_env="TEST_MIGRATION_DATABASE_URL", artifacts=artifacts, baseline=baseline)
    assert preservation.compare(baseline, current) == {"preserved": False,
        "changed_tables": ["app.projects"], "added_tables": [], "artifacts_preserved": False}


@pytest.mark.anyio
async def test_disposable_dump_restore_preserves_vectors_references_and_uncertain_charges(databases, test_urls):
    # The container service and database below are fixed; never substitute development.
    checked_test_urls(*(url.render_as_string(hide_password=False) for url in test_urls))
    owner, _ = databases
    async with owner.begin() as connection:
        await connection.execute(text("CREATE TABLE app.preservation_probe (id uuid PRIMARY KEY,project_id uuid REFERENCES app.projects(id),embedding vector(3))"))
        await connection.execute(text("INSERT INTO app.preservation_probe VALUES (:id,:id,'[0.1,0.2,0.3]')"), {"id": PA})
        profile = await connection.scalar(text("""INSERT INTO app.provider_profiles(provider,model,backend,role)
            VALUES ('groq','preservation-test','test','generation') RETURNING id"""))
        await connection.execute(text("""INSERT INTO app.cost_reservations(workspace_id,actor_id,profile_id,operation_hash,
            month,input_tokens,output_tokens,maximum_usd,status) VALUES (:workspace,:actor,:profile,:hash,
            '2026-11-01',1,1,0.123456789012,'uncertain')"""), {"workspace": WA,"actor": A,"profile": profile,"hash": "f"*64})
    try:
        async with owner.begin() as connection:
            before = await preservation_snapshot(connection)
        dump = await asyncio.to_thread(subprocess.run,
            ["docker","compose","exec","-T","test-db","pg_dump","-Fc","-U","docweave_admin","docweave_test"],
            cwd=REPO_ROOT, capture_output=True, timeout=30)
        assert dump.returncode == 0, "Disposable backup failed; private output withheld"
        async with owner.begin() as connection:
            await connection.execute(text("UPDATE app.preservation_probe SET embedding='[9,9,9]'"))
        restored = await asyncio.to_thread(subprocess.run,
            ["docker","compose","exec","-T","test-db","pg_restore","--clean","--if-exists","--exit-on-error",
                "-U","docweave_admin","-d","docweave_test"],
            cwd=REPO_ROOT, input=dump.stdout, capture_output=True, timeout=30)
        assert restored.returncode == 0, "Disposable restore failed; private output withheld"
        await owner.dispose()
        async with owner.begin() as connection:
            assert await preservation_snapshot(connection) == before
    finally:
        async with owner.begin() as connection:
            await connection.execute(text("DROP TABLE app.preservation_probe"))
