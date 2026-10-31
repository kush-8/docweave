"""Policy persistence; callers own transactions and connection lifetimes."""

from sqlalchemy import select, text
from docweave.db.models import Membership


async def membership_role(connection, actor):
    return await connection.scalar(select(Membership.role).where(
            Membership.user_id == actor.user_id, Membership.workspace_id == actor.workspace_id))


async def project_workspace(connection, values):
    return await connection.scalar(text("SELECT app.project_workspace(:project)"), values)


async def collection_workspace(connection, values):
    return await connection.scalar(text("SELECT app.collection_workspace(:collection)"), values)


async def collection_writable(connection, values):
    return await connection.scalar(text("SELECT app.collection_can(:collection,'write')"), values)
