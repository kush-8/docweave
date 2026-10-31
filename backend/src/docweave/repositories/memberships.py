from sqlalchemy import text


_LIST_SQL = {
    "members": text("SELECT * FROM app.list_members(:after,:id,:limit)"),
    "invitations": text("SELECT * FROM app.list_invitations(:after,:id,:limit)"),
}

async def owner_page(connection, kind, values):
    return await connection.execute(_LIST_SQL[kind], values)


async def update_member(connection, values):
    return await connection.execute(text("SELECT * FROM app.change_member(:user,:role)"), values)


async def remove_member(connection, values):
    return await connection.execute(text("SELECT * FROM app.change_member(:user,NULL)"), values)


async def create_invitation(connection, values):
    return await connection.execute(text("SELECT * FROM app.create_invitation(:email,:role,:hash)"), values)


async def revoke_invitation(connection, values):
    return await connection.execute(text("SELECT app.revoke_invitation(:id)"), values)


async def accept_invitation(connection, values):
    return await connection.execute(text("SELECT * FROM app.accept_invitation(:hash)"), values)
