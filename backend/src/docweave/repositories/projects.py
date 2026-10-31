from sqlalchemy import text


async def create_project(connection, values):
    return await connection.scalar(text("SELECT app.create_project(CAST(:context AS jsonb))"), values)


async def list_projects(connection, values):
    return await connection.execute(text("""
            SELECT p.id,p.created_at,app.project_view(p.id) AS project FROM app.projects p
            WHERE (CAST(:after AS timestamptz) IS NULL OR (p.created_at,p.id)>(:after,:id))
            ORDER BY p.created_at,p.id LIMIT :limit
        """), values)


async def get_project(connection, values):
    return await connection.scalar(text("SELECT app.project_view(:project)"), values)


async def update_project(connection, values):
    return await connection.scalar(text("SELECT app.update_project(:project,:revision,CAST(:context AS jsonb))"), values)
