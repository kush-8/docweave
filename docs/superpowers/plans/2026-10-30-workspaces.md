# Backend workspace creation, listing and access boundaries

The user authorized this next backend slice after reviewing its scope: atomic workspace/owner creation, actor-filtered listing, reusable membership/role checks, and tenant denial tests. Confirmed behavior is in `docs/architecture.md`, Task 1 of `docs/tasks.md`, and the existing workspace operations/schemas in `backend/openapi.yaml`. Frontend, invitations, membership mutation/last-owner handling and project CRUD remain separate work.

Using Superpowers planning/TDD/inline execution and Ponytail's smallest complete implementation. Continue on the existing `codex/auth` branch, preserving its uncommitted auth work and unrelated frontend/doc edits. No dependency additions, development database reset or migration, publishing or deployment.

## Design and file scope

- `backend/src/docweave/workspaces.py`: implement `POST /api/v1/workspaces` with strict nonblank-name input and HTTP 201 workspace response; implement `GET /api/v1/workspaces` with default 25/max 100 items and authenticated opaque keyset cursors. Current membership is reapplied on every page. Cursors bind to actor, workspace-list resource and `(created_at,id)` order using the existing Fernet key.
- `backend/alembic/versions/0003_workspaces.py`: atomic workspace+owner creation and own-workspace listing through fixed-search-path, runtime-only SECURITY DEFINER functions. Read actor ID from transaction context, never a client-provided owner field. Keep domain DML denied and existing selected-workspace RLS unchanged. Index memberships by user for listing.
- `backend/src/docweave/db.py`: allow the existing transaction helper to carry actor-only context with an empty selected workspace for these narrow functions; selected-tenant reads stay unchanged.
- `backend/src/docweave/policy.py`: immutable `Actor(user_id,workspace_id)`, `require_actor(request)` and `require_owner(request)` from verified sessions and current DB membership. Nonexistent/nonmember workspaces return the same safe 404; visible insufficient roles return 403/forbidden. Do not cache membership across requests or trust role/actor fields in request payloads.
- `backend/src/docweave/main.py`: register the two real operations; protect reserved `/workspaces/{workspace_id}/...` operations with membership checks and owner checks where their contracts require it. Keep origin/CSRF on mutations and existing auth errors. Document cookie AND CSRF for real POST operation.
- Tests: `backend/tests/test_workspaces.py`, affected auth/API/database checks, model/schema alignment. Docs: API/runtime status, workspace runbook, task/memory evidence.

## Execution

- [x] Run the current backend baseline; write workspace tests and observe failure from reserved routes/missing policy.
- [x] Implement narrow DB functions, optional actor-only context, route models/cursors and policy guards; run targeted tests.
- [x] Verify transaction rollback, general DML denial, unchanged tenant RLS, stable pagination, cursor tampering/cross-user use, membership/role revocation and safe errors.
- [x] Update runtime/draft docs and evidence, run the entire backend suite and migration/config/lock checks, request an independent read-only review and address material findings.

## Boundaries and learning check

Identity establishes who is signed in. Membership establishes which workspace they may access. Creating a workspace adds exactly one owner membership in the same transaction. An authenticated outsider requesting another workspace's reserved child route receives 404 before the handler, without its name. Owner status is checked from the database on each request; changing it affects the next request. Existing invitation/member/project operations stay 501 after applicable checks.

Database tests use only the guarded disposable `127.0.0.1:55433/docweave_test`. Original development credentials still require recovery; this does not prevent isolated verification. No social-provider or SMTP smoke is needed for this slice because the OIDC implementation is not changing.

## Final evidence — 2026-10-30

- Baseline: `uv run --project backend --locked --cache-dir backend/.uv-cache pytest backend/tests -q -W error` -> **226 passed**.
- RED: the first new creation test observed HTTP 501 instead of expected 201 before implementation.
- GREEN: initial workspace slice -> **23 passed**. The full suite exposed two stale auth/runtime-doc 501 expectations, updated to implemented 200/201 behavior.
- Independent review found no permission, cursor, atomicity or selected-tenant RLS defect. It reported one P2 validation issue: names containing NUL reached PostgreSQL. The added regression observed 500, then input validation was fixed to return safe 422 without inserts; all nine strict-input cases passed.
- Final full backend run -> **253 passed**, warnings as errors. Includes metadata/migration alignment, upgrade/downgrade/re-upgrade, runtime role and function permissions, actor-only context cleanup, equal-time ordering, cursor tampering/actor binding and current membership/owner-role checks.
- Locked offline uv sync, Compose validation and whitespace checks passed. No new dependencies, frontend implementation, live provider calls or development database mutation.
- Original development credentials still require restoration. Existing auth/unrelated frontend/doc work is preserved in the working tree on `codex/auth`; no merge, push or deployment was performed.
