"""Read-only preflight: python -m docweave.ownership [--mapping owner-map.json]."""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID
from sqlalchemy import text
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.services.ownership import inspect_ownership


async def check(mapping_path=None):
    overrides = {}
    if mapping_path:
        data = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Owner mapping must be a project UUID to user UUID object")
        overrides = {UUID(project): UUID(owner) for project, owner in data.items()}
    engine = make_engine(database_url("MIGRATION_DATABASE_URL"))
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            mapping = await inspect_ownership(connection, overrides)
            return {"projects": len(mapping), "owners": len(set(mapping.values())), "ready": True}
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Read-only personal ownership migration preflight")
    parser.add_argument("--mapping", help="Explicit project UUID to existing user UUID mapping JSON")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(check(args.mapping))))
    except ValueError as error:
        parser.exit(2, f"Ownership preflight failed: {error}\n")
    except Exception:
        parser.exit(2, "Ownership preflight unavailable; check migration access and database status.\n")


if __name__ == "__main__":
    main()
