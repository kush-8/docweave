from sqlalchemy import text


async def overdue(connection):
    return await connection.scalar(text('SELECT app.retention_overdue()'))
