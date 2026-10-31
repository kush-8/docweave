"""Read-only database/artifact fingerprints for backup and migration rehearsal."""
import argparse
import asyncio
import json
import re
from pathlib import Path

from sqlalchemy import text

from docweave.core.settings import database_url, storage_root
from docweave.db.engine import make_engine
from docweave.evaluation.reports import write_report
from docweave.repositories.ownership import preservation_snapshot
from docweave.storage.artifacts import snapshot_artifacts


def validate_snapshot(snapshot):
    try:
        if snapshot["format"] != "preservation-v1" or not snapshot["database"]:
            raise ValueError
        for table, entry in snapshot["database"].items():
            if (not isinstance(table, str) or not isinstance(entry["columns"], list) or not entry["columns"]
                or type(entry["rows"]) is not int or entry["rows"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                raise ValueError
        for path, digest in snapshot["artifacts"].items():
            if not isinstance(path, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Invalid preservation baseline") from None


async def capture(*, url_env="MIGRATION_DATABASE_URL", artifacts=None, baseline=None):
    if baseline is not None:
        validate_snapshot(baseline)
    engine = make_engine(database_url(url_env))
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            database = await preservation_snapshot(connection, baseline=baseline["database"] if baseline else None)
            files = snapshot_artifacts(artifacts if artifacts is not None else storage_root())
            return {"format": "preservation-v1", "database": database, "artifacts": files}
    finally:
        await engine.dispose()


def compare(baseline, current):
    validate_snapshot(baseline)
    validate_snapshot(current)
    changed = sorted(key for key, value in baseline["database"].items() if current["database"].get(key) != value)
    artifacts = baseline["artifacts"] == current["artifacts"]
    return {"preserved": not changed and artifacts, "changed_tables": changed,
        "added_tables": sorted(current["database"].keys() - baseline["database"].keys()), "artifacts_preserved": artifacts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", help="Save private fingerprints outside the artifact directory; does not create a backup")
    mode.add_argument("--compare", help="Compare restored data against a saved snapshot; exits 1 on drift")
    parser.add_argument("--artifacts", type=Path, default=storage_root(), help="Original or restored artifact directory")
    parser.add_argument("--database-url-env", default="MIGRATION_DATABASE_URL")
    args = parser.parse_args()
    try:
        baseline = None
        if args.compare:
            with Path(args.compare).open("rb") as file:
                content = file.read(64 * 1024 * 1024 + 1)
            if len(content) > 64 * 1024 * 1024:
                raise ValueError("Oversized preservation baseline")
            baseline = json.loads(content)
        if args.snapshot and Path(args.snapshot).resolve().is_relative_to(args.artifacts.resolve()):
            raise ValueError("Save fingerprints outside the artifact directory")
        snapshot = asyncio.run(capture(url_env=args.database_url_env, artifacts=args.artifacts, baseline=baseline))
        if baseline is not None:
            result = compare(baseline, snapshot)
        else:
            write_report(args.snapshot, snapshot)
            result = {"captured": True, "tables": len(snapshot["database"]), "artifacts": len(snapshot["artifacts"])}
        print(json.dumps(result))
        if result.get("preserved") is False:
            parser.exit(1)
    except Exception:
        parser.exit(2, "Preservation check unavailable; check private inputs, database access and artifact paths.\n")


if __name__ == "__main__":
    main()
