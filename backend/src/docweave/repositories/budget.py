from sqlalchemy import text


async def reserve_cost(connection, values):
    return await connection.scalar(text("SELECT app.reserve_cost(:key,:profile,:input,:output,:project)"), values)


async def settle_cost(connection, values):
    return await connection.scalar(text("SELECT app.settle_cost(:id,:actual,:uncertain)"), values)


async def usage(connection, values):
    return await connection.scalar(text("SELECT app.usage_report(CAST(:month AS date),:project)"), values)
