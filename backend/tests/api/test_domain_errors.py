"""Domain failures retain safe HTTP contracts after leaving the request layer."""

import pytest
from httpx import ASGITransport, AsyncClient

from docweave.core.errors import DomainError
from docweave.main import create_app


@pytest.mark.anyio
@pytest.mark.parametrize(("code", "status", "retryable"), [
    ("forbidden", 403, False), ("revision_conflict", 409, False),
    ("rate_limited", 429, True), ("unknown_internal_code", 500, False),
])
async def test_domain_failures_keep_status_headers_and_safe_envelope(code, status, retryable):
    app = create_app()

    @app.get("/domain-error")
    async def fail():
        raise DomainError(code, headers={"Retry-After": "60"} if code == "rate_limited" else None)

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.get("/domain-error")
    assert response.status_code == status
    result = response.json()
    assert result["code"] == ("internal_error" if code == "unknown_internal_code" else code)
    assert result["retryable"] is retryable
    assert result["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "unknown_internal_code" not in response.text
    if code == "rate_limited":
        assert response.headers["Retry-After"] == "60"
