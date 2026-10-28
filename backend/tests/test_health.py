"""First runtime TDD test: liveness must work without an authenticated session."""

import asyncio

from httpx import ASGITransport, AsyncClient


def test_liveness_returns_ok_without_login():
    from docweave.main import create_app

    async def get_liveness():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            return await client.get("/api/v1/health/live")

    response = asyncio.run(get_liveness())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
