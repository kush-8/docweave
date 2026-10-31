from sqlalchemy import text


async def create_workspace(connection, values):
    return await connection.execute(text("SELECT * FROM app.create_workspace(:name)"), values)


async def list_workspaces(connection, values):
    return await connection.execute(text("SELECT * FROM app.list_workspaces(:after,:id,:limit)"), values)
