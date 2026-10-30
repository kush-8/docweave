# Backend workspaces

Implemented 2026-10-30, backend only. Requires [auth](auth.md) and migration `0003_workspaces`. The subsequent [membership slice](memberships.md), revision `0004_memberships`, now implements invitations, member roles/removal and last-owner protection. Frontend, project CRUD and complete Task 1 remain unfinished.

## Implemented operations

`POST /api/v1/workspaces` requires a valid session, exact configured Origin and `X-CSRF-Token` from `/me`. Send only a nonblank `name`; surrounding whitespace is trimmed, NUL characters and extra fields are rejected with safe 422 errors. Actor, role, budget and membership cannot be supplied by the caller.

```json
{"name":"Engineering"}
```

HTTP 201 returns `id`, `name`, `role: "owner"`, and UTC `created_at`. The workspace and exactly one membership for the signed-in actor are committed together. If the membership insert fails, no workspace remains. No spending allowance, project, provider call or paid work is created.

`GET /api/v1/workspaces` returns only current memberships, including the actor's role in each workspace:

```json
{"items":[],"next_cursor":null}
```

Pagination defaults to 25 items, accepts `limit` from 1–100 and orders ascending by `(created_at,id)`, including equal timestamps. Follow the opaque `next_cursor` as a query parameter; null ends pagination. A cursor is encrypted/authenticated with the existing auth key and binds to the actor, workspace-list resource and last ordering tuple. Changing keys invalidates old cursors. Malformed/tampered/other-actor cursors return 400/`invalid_cursor`; empty/oversized cursors or invalid limits return 422. The same user's new session may reuse a cursor. Membership is queried again on every page: revocation removes access immediately on the next request, and role changes are reflected.

Both endpoints return `Cache-Control: no-store` and server-generated request IDs. Runtime OpenAPI describes the implemented 200/201 responses and requires cookie AND CSRF for POST. The existing YAML remains the target for deferred domain operations.

## Reusable access checks

`policy.Actor` contains only verified user/workspace UUIDs. `require_actor(request)` uses the verified session and the `workspace_id` path parameter, then checks current membership through tenant RLS. Client headers, query parameters, body actor IDs and claimed roles do not grant access. Malformed, nonexistent and nonmember workspace targets return safe 404 without their names.

`require_owner(request)` rechecks the current database role. A visible workspace with insufficient role returns 403/`forbidden`; a revoked membership returns 404. These guards now protect the reserved workspace child operations:

| Reserved route | Required workspace authority |
| --- | --- |
| Member and invitation operations | Owner |
| Create project | Owner |
| List projects and view own-workspace usage | Current member |

Member/invitation handlers are now implemented through transactionally rechecked functions; reserved project/usage handlers still return 501 after these checks. Mutations require origin/CSRF. Global project/resource policy and collection grants remain future work; request guards do not replace transactional/background authority checks.

## Database boundary and verification

Runtime retains no general INSERT/UPDATE/DELETE grant on workspace or membership tables. Narrow runtime-only, fixed-search-path SECURITY DEFINER functions create the workspace/owner pair and list only the transaction actor's memberships. Neither accepts a caller-provided actor argument. PUBLIC has no EXECUTE grant. The new membership-user index supports listing.

`tenant_session(engine, actor_id=..., workspace_id=None)` sets actor-only context with an empty selected workspace. Only the narrow functions can perform the new operations under that context; ordinary workspace/membership/project SELECTs still return no rows until an authorized workspace is selected. Existing tenant RLS is unchanged, and pooled transaction context clears on commit/rollback.

After restoring the original development credentials, apply migrations using the [database runbook](database.md). The preserved development volume was not migrated or reset for this task; verification uses only the guarded disposable service:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests/test_workspaces.py -q -W error
uv run --project backend --locked pytest backend/tests -q -W error
docker compose --profile test stop test-db
```

Tests use real signed test OIDC tokens and restricted PostgreSQL connections. They cover atomic creation/rollback, strict inputs/CSRF, membership filtering/revocation, equal-time pagination, cursor tampering/other actors, owner demotion, forged actor claims, function permissions, selected-tenant RLS and actor-only pooled-context cleanup. Full-suite migration tests downgrade/re-upgrade the disposable schema and compare model metadata; no production/persistent database verification is claimed.

Failure walkthrough: Alice signs in and requests Bob's `/workspaces/{id}/projects`. Her session proves her identity. The policy selects Bob's workspace only for a transaction and asks for Alice's current membership. RLS returns no row, so the request returns 404 before the reserved handler, without Bob's name. Alice becoming an owner elsewhere does not change that result.
