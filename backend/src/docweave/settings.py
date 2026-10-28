"""Explicit database credentials; importing the API does not require a database."""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import make_url
from sqlalchemy.engine import URL
from sqlalchemy.exc import ArgumentError


def database_url(name: str) -> URL:
    value = os.environ.get(name)
    if value is None:
        value = dotenv_values(Path(__file__).resolve().parents[3] / ".env").get(name)
    if not value:
        raise ValueError(f"{name} must be set")
    try:
        url = make_url(value)
        if url.drivername != "postgresql+asyncpg" or not all((url.host, url.database, url.username, url.password)):
            raise ValueError
    except (ArgumentError, ValueError):
        raise ValueError(f"{name} must be a complete postgresql+asyncpg connection URL") from None
    return url
