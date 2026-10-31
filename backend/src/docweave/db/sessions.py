from contextlib import asynccontextmanager
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.exc import DBAPIError
from docweave.core.errors import DomainError, BudgetError
from docweave.repositories.errors import SQL_ERRORS, BUDGET_ERRORS


@asynccontextmanager
async def tenant_session(engine: AsyncEngine, *, actor_id: UUID, workspace_id: UUID | None = None):
    # Callers must obtain these IDs from verified identity/policy, never request claims.
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        await session.execute(text(
            "SELECT set_config('docweave.actor_id', :actor, true), "
            "set_config('docweave.workspace_id', :workspace, true)"
        ), {"actor": str(actor_id), "workspace": str(workspace_id) if workspace_id is not None else ""})
        yield session


@asynccontextmanager
async def domain_session(engine, actor_id, workspace_id=None):
    try:
        async with tenant_session(engine, actor_id=actor_id, workspace_id=workspace_id) as session:
            yield session
    except DBAPIError as error:
        code = SQL_ERRORS.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise DomainError(code) from None
        raise


@asynccontextmanager
async def budget_session(engine, *, actor_id, workspace_id):
    try:
        async with tenant_session(engine, actor_id=actor_id, workspace_id=workspace_id) as session:
            yield session
    except DBAPIError as error:
        code = BUDGET_ERRORS.get(getattr(error.orig, "sqlstate", None))
        if code:
            raise BudgetError(code) from None
        raise
