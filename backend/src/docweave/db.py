"""Runtime sessions scope actor/tenant context to exactly one transaction."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


def make_engine(url: URL) -> AsyncEngine:
    return create_async_engine(
        url, pool_pre_ping=True, hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 10},
    )


@asynccontextmanager
async def tenant_session(engine: AsyncEngine, *, actor_id: UUID, workspace_id: UUID | None = None):
    # Callers must obtain these IDs from verified identity/policy, never request claims.
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        await session.execute(text(
            "SELECT set_config('docweave.actor_id', :actor, true), "
            "set_config('docweave.workspace_id', :workspace, true)"
        ), {"actor": str(actor_id), "workspace": str(workspace_id) if workspace_id is not None else ""})
        yield session
