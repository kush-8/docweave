"""Resolve legacy ownership before any data-changing migration."""
from uuid import UUID
import re


def ownership_mapping(projects, overrides=None, *, users=None):
    overrides = overrides or {}
    project_ids = {row["project_id"] for row in projects}
    if set(overrides) - project_ids:
        raise ValueError("Owner mapping contains an unknown project")
    result = {}
    for row in projects:
        identity = row["project_id"]
        owners = set(row["owners"] or [])
        existing = row.get("owner_user_id")
        if existing is not None and identity in overrides and overrides[identity] != existing:
            raise ValueError("Project owner is already assigned")
        owner = existing or overrides.get(identity)
        if owner is None:
            if len(owners) != 1:
                raise ValueError(f"Project {identity} requires an explicit owner mapping")
            owner = next(iter(owners))
        if not isinstance(identity, UUID) or not isinstance(owner, UUID):
            raise ValueError("Project and owner identities must be UUIDs")
        if users is not None and owner not in users:
            raise ValueError("Owner mapping contains an unknown user")
        result[identity] = owner
    return result


async def inspect_ownership(connection, overrides=None):
    """Caller must use a read-only migration-role transaction; no data is changed."""
    from docweave.repositories.ownership import ownership_rows
    rows, users = await ownership_rows(connection)
    return ownership_mapping(rows, overrides, users=users)


def parse_identity_plan(data):
    """Private operator manifest; tokens are environment references, never file values."""
    try:
        if set(data) != {"identities", "projects", "retained_users"}:
            raise ValueError
        identities = {}
        for key, entry in data["identities"].items():
            if set(entry) != {"issuer", "subject", "github_id", "token_env"}:
                raise ValueError
            if (type(entry["github_id"]) is not int or entry["github_id"] <= 0
                or any(not isinstance(entry[k], str) or not entry[k].strip() for k in ("issuer", "subject", "token_env"))
                or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", entry["token_env"])):
                raise ValueError
            identities[UUID(key)] = dict(entry)
        projects = {UUID(key): UUID(value) for key, value in data["projects"].items()}
        if not isinstance(data["retained_users"], list):
            raise ValueError
        retained = {UUID(value) for value in data["retained_users"]}
        if (retained & identities.keys() or len(retained) != len(data["retained_users"])
            or len(identities) != len(data["identities"]) or len(projects) != len(data["projects"])):
            raise ValueError
        return {"identities": identities, "projects": projects, "retained_users": retained}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Invalid identity mapping") from None


async def apply_identity_plan(connection, plan, github, tokens, *, apply=False):
    """Caller owns the outer transaction; verify every link before any writes."""
    from docweave.repositories import ownership as repository

    for entry in plan["identities"].values():
        token = tokens.get(entry["token_env"])
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Identity verification token is unavailable")
        identity = await github.user(token)
        if type(identity.get("id")) is not int or identity["id"] != entry["github_id"]:
            raise ValueError("Verified GitHub identity does not match mapping")

    async with connection.begin_nested():
        await repository.cutover_tables(connection, lock=apply)
        if apply and not await repository.cutover_is_drained(connection):
            raise ValueError("Drain workers and reconcile running jobs before identity cutover")
        rows = {row["id"]: row for row in await repository.identity_rows(connection)}
        mapped, retained = plan["identities"], plan["retained_users"]
        if (mapped.keys() | retained) - rows.keys():
            raise ValueError("Identity mapping contains an unknown user")
        if any(row["issuer"] not in ("https://github.com", "docweave:service")
            and key not in mapped and key not in retained for key, row in rows.items()):
            raise ValueError("Legacy users require an explicit mapping or retention decision")
        pending = {}
        targets = set()
        for key, entry in mapped.items():
            row = rows[key]
            target = ("https://github.com", str(entry["github_id"]))
            if target in targets or any(other != key and (r["issuer"], r["subject"]) == target for other, r in rows.items()):
                raise ValueError("GitHub identity is already assigned; user merging is forbidden")
            targets.add(target)
            current = (row["issuer"], row["subject"])
            if current == target:
                continue
            if row["issuer"] in ("https://github.com", "docweave:service") or current != (entry["issuer"], entry["subject"]):
                raise ValueError("Existing identity changed or cannot be relinked")
            pending[key] = entry
        projects = await inspect_ownership(connection, plan["projects"])
        for owner in projects.values():
            row = rows[owner]
            if owner in retained or (owner not in mapped and
                (row["issuer"] != "https://github.com" or not re.fullmatch(r"[1-9][0-9]*", row["subject"]))):
                raise ValueError("Every project owner requires a verified numeric GitHub identity")
        result = {"projects": len(projects), "identities": len(mapped), "retained_users": len(retained), "applied": apply}
        if apply:
            expected = await repository.preservation_snapshot(connection, identities=pending, projects=projects)
            await repository.write_identity_links(connection, pending, projects)
            actual = await repository.preservation_snapshot(connection)
            if actual != expected:
                raise ValueError("Preservation comparison failed; identity changes rolled back")
            result["preserved"] = True
        return result
