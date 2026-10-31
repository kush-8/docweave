from sqlalchemy import text


async def list_collections(connection, values):
    return await connection.execute(text("""
            SELECT c.id,c.created_at,c.project_id,c.name,app.collection_can(c.id,'write') AS can_write FROM app.collections c
            WHERE c.project_id=:project AND (CAST(:after AS timestamptz) IS NULL OR (c.created_at,c.id)>(:after,:id))
            ORDER BY c.created_at,c.id LIMIT :limit
        """), values)


async def create_collection(connection, values):
    return await connection.scalar(text("SELECT app.create_collection(:project,:name)"), values)


async def get_grants(connection, values):
    return await connection.scalar(text("SELECT app.collection_grants(:collection)"), values)


async def replace_grants(connection, values):
    return await connection.scalar(text("SELECT app.replace_collection_grants(:collection,:revision,CAST(:grants AS jsonb))"), values)


async def read_policy(connection, values):
    return await connection.scalar(text("SELECT app.processing_policy(:kind,:id)"), values)


async def replace_policy(connection, values):
    return await connection.scalar(text("SELECT app.replace_processing_policy(:kind,:id,:revision,CAST(:processors AS jsonb))"), values)
