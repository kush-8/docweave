# API Skeleton Implementation Plan

> Execute inline with Superpowers TDD; the user authorized tests first, then all draft operations, with no database, AI, or business logic.

**Goal:** Run a FastAPI skeleton covering all 69 operations in `backend/openapi.yaml`.
**Spec:** The current user request and `backend/openapi.yaml`; the broader tasks remain deferred.
**Architecture:** A `create_app()` factory, a static feature-route table, and shared safe error responses. Runtime OpenAPI describes the skeleton; the draft remains the future feature contract. No runtime YAML loading, fabricated records, authentication bypass, persistence, jobs, or provider calls.
**Tech stack:** Existing Python 3.12/pytest/HTTPX; add only FastAPI and Uvicorn runtime dependencies with uv.

## Scope and decisions

- The user selected every draft operation. Liveness returns 200/`{"status":"ok"}`; readiness returns 503 while required services are absent; all 67 feature operations return 501/`not_implemented`.
- No feature request is processed or accepted. Input/business validation and authentication are deferred with those features, and this skeleton must not be presented as a usable product API.
- Include a safe error envelope, server-generated request IDs, no-store responses, 404 for unknown routes, 405 with Allow for wrong methods, and safe unexpected errors.
- Use the existing checkout: its uncommitted tests and concurrent frontend work must be preserved. No commit, branch, or frontend change is part of this request.
- Keep full implementation milestones unchecked. A route skeleton does not establish runtime security or readiness.

## Tasks and evidence

- [x] Write runtime tests for health, every draft feature method/path, safe errors/headers, and generated OpenAPI coverage. Run before any production code and observe RED from the missing app.
- [x] Implement the minimal factory, health endpoints, shared errors, and explicit feature-route table. Run the full backend suite and require GREEN.
- [x] Verify an actual local Uvicorn process, update run/test instructions and handoff evidence, and request a bounded independent review.

## Progress

Plan recorded before implementation. Existing baseline: 70 contract checks pass and the first liveness test fails because `docweave.main` is missing.

RED: 75 runtime failures, 70 contract passes; representative focused failure was `ModuleNotFoundError: No module named 'docweave.main'`.

GREEN: `uv run --offline --locked --project backend pytest backend/tests -q -W error` passed all 145 checks. Runtime tests use the existing HTTPX ASGI transport and AnyIO's asyncio backend; no deprecated TestClient adapter or added HTTP client was needed.

Environment note: Windows sandbox asyncio blocked on its internal socket pair before HTTP dispatch. Verification passed with local-loopback permission; no application workaround was added. Bare full-suite discovery and an actual local server are also checked before handoff.

Live smoke: temporary Uvicorn on an allocated localhost port returned liveness 200, readiness 503, feature 501, unknown route 404; `/docs` returned 200 and runtime OpenAPI contained 69 operations. Server terminated in a finally block. A fresh read-only review found no material code issues. Business/security/database/AI behavior was explicitly outside review scope.
