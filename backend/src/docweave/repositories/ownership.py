"""Read-only legacy ownership inventory."""
from sqlalchemy import text

async def ownership_rows(connection):
    rows = (await connection.execute(text("""SELECT p.id AS project_id,
        coalesce(array_agg(m.user_id) FILTER (WHERE m.role='owner'), '{}') AS owners
        FROM app.projects p LEFT JOIN app.memberships m ON m.workspace_id=p.workspace_id
        GROUP BY p.id ORDER BY p.id"""))).mappings().all()
    users = set((await connection.execute(text("SELECT id FROM app.users"))).scalars())
    return rows, users
