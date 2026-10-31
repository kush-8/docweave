"""Operator preflight/linking: python -m docweave.ownership --help."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID
from sqlalchemy import text
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.services.ownership import inspect_ownership
from docweave.services.ownership import apply_identity_plan, parse_identity_plan
from docweave.integrations.github import GitHubClient


def load_mapping(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate identity mapping key")
            result[key] = value
        return result
    try:
        with Path(path).open("rb") as file:
            content = file.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError
        return json.loads(content.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise ValueError("Invalid or oversized mapping JSON") from None


async def check(mapping_path=None, *, identity_mapping_path=None, apply=False, url_env="MIGRATION_DATABASE_URL"):
    if (mapping_path and identity_mapping_path) or (apply and not identity_mapping_path):
        raise ValueError("Apply requires an identity mapping; mapping modes cannot be combined")
    overrides = {}
    if mapping_path:
        data = load_mapping(mapping_path)
        if not isinstance(data, dict):
            raise ValueError("Owner mapping must be a project UUID to user UUID object")
        try:
            overrides = {UUID(project): UUID(owner) for project, owner in data.items()}
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Owner mapping must contain UUIDs") from None
    plan = parse_identity_plan(load_mapping(identity_mapping_path)) if identity_mapping_path else None
    engine = make_engine(database_url(url_env))
    try:
        async with engine.begin() as connection:
            if not apply:
                await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            if plan is not None:
                return await apply_identity_plan(connection, plan, GitHubClient(None), os.environ, apply=apply)
            mapping = await inspect_ownership(connection, overrides)
            return {"projects": len(mapping), "owners": len(set(mapping.values())), "ready": True,
                "scope": "project_ownership_only", "applied": False}
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="UUID-preserving personal ownership preflight; read-only unless --apply")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mapping", help="Explicit project UUID to existing user UUID mapping JSON (read-only)")
    group.add_argument("--identity-mapping", help="Private identity/project/retained-user manifest; verifies GitHub /user")
    parser.add_argument("--apply", action="store_true", help="Apply verified manifest after backup/restore rehearsal and worker drain")
    parser.add_argument("--database-url-env", default="MIGRATION_DATABASE_URL", help="Environment variable containing the migration URL")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(check(args.mapping, identity_mapping_path=args.identity_mapping,
            apply=args.apply, url_env=args.database_url_env))))
    except ValueError as error:
        parser.exit(2, f"Ownership preflight failed: {error}\n")
    except Exception:
        parser.exit(2, "Ownership preflight unavailable; check migration access and database status.\n")


if __name__ == "__main__":
    main()
