"""Resolve legacy ownership before any data-changing migration."""
from uuid import UUID


def ownership_mapping(projects, overrides=None, *, users=None):
    overrides = overrides or {}
    project_ids = {row["project_id"] for row in projects}
    if set(overrides) - project_ids:
        raise ValueError("Owner mapping contains an unknown project")
    result = {}
    for row in projects:
        identity = row["project_id"]
        owners = set(row["owners"] or [])
        owner = overrides.get(identity)
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
