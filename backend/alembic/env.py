"""Migrations use owner credentials explicitly, never API startup."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from docweave.models import Base
from docweave.settings import database_url


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      include_schemas=True, version_table_schema="app")
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(database_url("MIGRATION_DATABASE_URL"), poolclass=pool.NullPool,
                                 hide_parameters=True, connect_args={"timeout": 5, "command_timeout": 30})
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
elif context.is_offline_mode():
    context.configure(url=database_url("MIGRATION_DATABASE_URL"), target_metadata=Base.metadata,
                      literal_binds=True, include_schemas=True, version_table_schema="app")
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
