"""Operator-only ownership inventory and UUID-preserving identity updates."""
import hashlib
import json

from sqlalchemy import text


async def require_migration_role(connection):
    if await connection.scalar(text("SELECT current_user")) != "docweave_migrator":
        raise ValueError("Ownership preservation requires the migration role")
    await connection.execute(text("SET LOCAL row_security=off"))


async def ownership_rows(connection):
    await require_migration_role(connection)
    personal = await connection.scalar(text("""SELECT EXISTS(SELECT 1 FROM information_schema.columns
        WHERE table_schema='app' AND table_name='projects' AND column_name='owner_user_id')"""))
    owner = "p.owner_user_id" if personal else "NULL::uuid"
    rows = (await connection.execute(text(f"""SELECT p.id AS project_id, {owner} AS owner_user_id,
        coalesce(array_agg(m.user_id) FILTER (WHERE m.role='owner'), '{{}}') AS owners
        FROM app.projects p LEFT JOIN app.memberships m ON m.workspace_id=p.workspace_id
        GROUP BY p.id ORDER BY p.id"""))).mappings().all()
    users = set((await connection.execute(text("SELECT id FROM app.users"))).scalars())
    return rows, users


async def identity_rows(connection):
    return (await connection.execute(text("SELECT id,issuer,subject FROM app.users"))).mappings().all()


async def cutover_is_drained(connection):
    return not await connection.scalar(text("""SELECT
        EXISTS(SELECT 1 FROM app.personal_jobs WHERE status='running') OR
        EXISTS(SELECT 1 FROM app.catalog_jobs WHERE status='running') OR
        EXISTS(SELECT 1 FROM app.ingestion_jobs WHERE status='running') OR
        EXISTS(SELECT 1 FROM queue.procrastinate_jobs WHERE status='doing')"""))


async def cutover_tables(connection, *, lock=False):
    await require_migration_role(connection)
    tables = (await connection.execute(text("""SELECT schemaname,tablename FROM pg_tables
        WHERE schemaname IN ('app','queue') ORDER BY schemaname,tablename"""))).all()
    quote = connection.dialect.identifier_preparer.quote_identifier
    names = [f"{quote(schema)}.{quote(table)}" for schema, table in tables]
    if lock:
        await connection.execute(text("LOCK TABLE " + ",".join(names) + " IN SHARE ROW EXCLUSIVE MODE"))
    return list(zip(tables, names))


async def preservation_snapshot(connection, *, identities=None, projects=None, baseline=None):
    """Hash complete rows, including vectors/references/claims, without returning content.

    Optional mappings describe the exact expected cutover, not ignored columns.
    """
    await require_migration_role(connection)
    identities, projects = identities or {}, projects or {}
    links = {str(key): {"issuer": "https://github.com", "subject": str(value["github_id"])}
        for key, value in identities.items()}
    owners = {str(key): {"owner_user_id": str(value)} for key, value in projects.items()}
    result = {}
    columns = {}
    for schema, table, column in (await connection.execute(text("""SELECT table_schema,table_name,column_name
        FROM information_schema.columns WHERE table_schema IN ('app','queue') ORDER BY ordinal_position"""))).all():
        columns.setdefault(f"{schema}.{table}", []).append(column)
    if baseline is not None and (not isinstance(baseline, dict) or not baseline or baseline.keys() - columns.keys()):
        raise ValueError("Preservation baseline contains missing tables")
    for (schema, table), name in await cutover_tables(connection):
        key = f"{schema}.{table}"
        expression, where, values = "to_jsonb(t)", "", {}
        selected = columns[key]
        if baseline is not None and key in baseline:
            selected = baseline[key].get("columns")
            if (not isinstance(selected, list) or not selected or any(not isinstance(c, str) for c in selected)
                or len(set(selected)) != len(selected) or set(selected) - set(columns[key])):
                raise ValueError("Preservation baseline contains missing or invalid columns")
            expression += " - CAST(:omit AS text[])"
            values["omit"] = list(set(columns[key]) - set(selected))
        changes = links if (schema, table) == ('app', 'users') else owners if (schema, table) == ('app', 'projects') else {}
        if changes:
            expression += " || coalesce(CAST(:changes AS jsonb)->t.id::text, '{}'::jsonb)"
            values["changes"] = json.dumps(changes)
        if (schema, table) == ('app', 'auth_sessions') and identities:
            where = " WHERE NOT (t.user_id=ANY(:users))"
            values["users"] = list(identities)
        hashes = []
        async with connection.stream(text(f"SELECT ({expression})::text FROM {name} t{where}"), values) as stream:
            async for row in stream:
                hashes.append(hashlib.sha256(row[0].encode()).digest())
        result[key] = {"columns": selected, "rows": len(hashes),
            "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest()}
    return result


async def write_identity_links(connection, identities, projects):
    for identity, entry in identities.items():
        await connection.execute(text("UPDATE app.users SET issuer='https://github.com',subject=:subject WHERE id=:id"),
            {"id": identity, "subject": str(entry["github_id"])})
        await connection.execute(text("DELETE FROM app.auth_sessions WHERE user_id=:id"), {"id": identity})
    for project, owner in projects.items():
        await connection.execute(text("UPDATE app.projects SET owner_user_id=:owner WHERE id=:id AND owner_user_id IS NULL"),
            {"id": project, "owner": owner})
