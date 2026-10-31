from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(url: URL) -> AsyncEngine:
    return create_async_engine(
        url, pool_pre_ping=True, hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
