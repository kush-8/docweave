"""HTTP skeleton tests; feature operations must not simulate working business logic."""

import re
from pathlib import Path
from uuid import UUID

import pytest
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename


DRAFT, _ = read_from_filename(str(Path(__file__).resolve().parents[1] / "openapi.yaml"))
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
pytestmark = pytest.mark.anyio
OPERATIONS = [
    (method, path, operation["operationId"])
    for path, item in DRAFT["paths"].items()
    for method, operation in item.items()
    if method in METHODS
]


def assert_error(response, status, code, retryable=False):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"code", "message", "request_id", "retryable"}
    assert body["code"] == code
    assert body["message"]
    assert body["retryable"] is retryable
    assert body["request_id"] == response.headers["X-Request-ID"]
    UUID(body["request_id"])
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(("method", "path", "operation_id"), [
    operation for operation in OPERATIONS if not operation[1].startswith(("/health/", "/auth/")) and operation[1] != "/me"
], ids=lambda value: value)
async def test_anonymous_feature_operations_are_denied_or_publicly_reserved(client, method, path, operation_id):
    url = re.sub(r"\{[^}]+\}", "97f0d4a6-86c2-4bec-91cc-329f97d228d2", path)
    response = await client.request(method, f"/api/v1{url}")

    if path in ("/catalog", "/providers"):
        assert_error(response, 501, "not_implemented")
    else:
        assert_error(response, 401, "unauthenticated")


async def test_readiness_is_unavailable_until_required_services_exist(client):
    response = await client.get("/api/v1/health/ready")

    assert_error(response, 503, "not_ready", retryable=True)


async def test_liveness_has_unique_server_generated_request_ids(client):
    first = await client.get("/api/v1/health/live", headers={"X-Request-ID": "untrusted-id"})
    second = await client.get("/api/v1/health/live")

    assert first.status_code == second.status_code == 200
    UUID(first.headers["X-Request-ID"])
    UUID(second.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    assert first.headers["Cache-Control"] == "no-store"


async def test_unknown_route_returns_safe_not_found(client):
    response = await client.get("/api/v1/private-marker?secret=private-marker")

    assert_error(response, 404, "not_found")
    assert "private-marker" not in response.text


async def test_wrong_method_returns_method_not_allowed(client):
    response = await client.post("/api/v1/health/live")

    assert_error(response, 405, "method_not_allowed")
    assert "GET" in response.headers["Allow"]


async def test_stub_does_not_echo_private_content_or_issue_session_cookie(client):
    response = await client.post("/api/v1/workspaces", json={"name": "private-marker"})

    assert_error(response, 401, "unauthenticated")
    assert "private-marker" not in response.text
    assert "Set-Cookie" not in response.headers


async def test_unexpected_error_does_not_expose_exception_details(app, client):
    @app.get("/test-error", include_in_schema=False)
    async def fail():
        raise RuntimeError("private-marker")

    response = await client.get("/test-error")

    assert_error(response, 500, "internal_error")
    assert "private-marker" not in response.text


async def test_runtime_openapi_covers_draft_operations_with_honest_stub_responses(client):
    response = await client.get("/openapi.json")
    docs = await client.get("/docs")

    assert docs.status_code == response.status_code == 200
    schema = response.json()
    validate(schema)
    actual_operations = {
        (method, path)
        for path, item in schema["paths"].items()
        for method in item
        if method in METHODS
    }
    assert actual_operations == {(method, f"/api/v1{path}") for method, path, _ in OPERATIONS}
    for method, path, operation_id in OPERATIONS:
        operation = schema["paths"][f"/api/v1{path}"][method]
        assert operation["operationId"] == operation_id
        if path in ("/auth/login", "/auth/callback"):
            expected_status = "302"
        elif path in ("/health/live", "/me") or (path == "/workspaces" and method == "get") or operation_id in {"listMembers", "listInvitations", "updateMemberRole", "acceptInvitation", "listProjects", "getProject", "updateProject"}:
            expected_status = "200"
        elif (path == "/workspaces" and method == "post") or operation_id in {"createInvitation", "createProject"}:
            expected_status = "201"
        else:
            expected_status = "204" if path == "/auth/logout" or operation_id in {"removeMember", "revokeInvitation"} else "503" if path == "/health/ready" else "501"
        assert expected_status in operation["responses"]


async def test_runtime_openapi_declares_cookie_and_csrf_together(client):
    schema = (await client.get("/openapi.json")).json()
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [{"sessionCookie": []}]
    assert schema["paths"]["/api/v1/auth/logout"]["post"]["security"] == [{"sessionCookie": [], "csrfToken": []}]
    assert schema["paths"]["/api/v1/workspaces"]["post"]["security"] == [{"sessionCookie": [], "csrfToken": []}]
    for path, method in [("/workspaces/{workspace_id}/invitations", "post"), ("/workspaces/{workspace_id}/members/{user_id}", "patch"),
                         ("/workspaces/{workspace_id}/members/{user_id}", "delete"), ("/invitations/{token}/accept", "post")]:
        assert schema["paths"]["/api/v1" + path][method]["security"] == [{"sessionCookie": [], "csrfToken": []}]
    assert "422" in schema["paths"]["/api/v1/auth/login"]["get"]["responses"]
