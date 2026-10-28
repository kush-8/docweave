# Database foundation and core tables

Approved by the user on 2026-10-29; execute inline using Superpowers TDD.

## Binding scope

Local PostgreSQL 17/pgvector 0.8.7, async SQLAlchemy/asyncpg, Alembic, and users/workspaces/memberships/projects. Separate administrator, migration owner, and SELECT-only runtime credentials. Development storage persists on localhost:55432; the separate docweave_test instance uses temporary storage on localhost:55433. No automatic startup migrations, API persistence, authentication, AI, business authorization, or readiness change.

UUID keys, UTC timestamps, named constraints, unique issuer/subject and memberships, checked roles/nonblank fields/positive revisions/JSONB arrays, restrictive foreign keys. Runtime reads use transaction-local actor/workspace context plus membership-backed RLS. Tests connect with actual restricted credentials, not a table owner. Test targets must be explicitly configured and cannot be the development database.

## Execution ledger

- [x] Write connection/configuration, migration, constraints, transaction, isolation, pool-context, and privilege tests; observe RED before source/migration implementation.
- [x] Add only required uv-locked dependencies, Compose/bootstrap/environment example, and resolve the approved image digest. Generate local ignored credentials without printing them.
- [x] Implement models, explicit reversible migrations, and transaction-scoped sessions; verify GREEN against the disposable database.
- [x] Migrate the development database without resetting it; verify Compose, real connections, full tests, and independent review. Document start/stop/migrate/test without development-volume deletion.

Existing checkout is retained to preserve the API skeleton and unrelated concurrent changes; no commit or branch is part of this slice. Existing 145 API/contract checks must remain green. Docker Desktop was stopped initially; starting it is authorized by the approved local setup. Only test storage may be reset. No project milestone is complete merely because tables exist.

## Verification evidence

- Tests were written before database source/migrations. Initial focused RED: 4 configuration tests failed because `docweave.settings` was missing; 6 guard checks passed. Configuration then passed all 10 focused checks.
- Real PostgreSQL tests exposed a downgrade dependency failure: RLS policies referenced memberships. Explicit policy removal before table drops made downgrade/re-upgrade pass. Alembic's installed version also required `path_separator=os` to avoid a deprecation warning.
- Independent review found one P1 in the test-target guard: asyncpg URL query overrides could route destructive tests to the development database. Five synthetic tests reproduced the issue without connecting; strict query-free test URLs and the exact approved local endpoint fixed it. Positive approved-pair coverage was added.
- A further failing test demonstrated that loading all dotenv entries exported administrator credentials into the process environment. Configuration now returns only the requested URL without changing the environment; the test passes.
- Final database suite: 51 passed with warnings treated as errors. Final bare full suite from backend: `uv run --offline --locked pytest -q -W error` -> 196 passed. No tests were skipped.
- Compose configuration passed. Development was newly initialized and migrated to `0001_core`; `alembic check` found no schema drift. Its migration revision and row counts survived a container restart without modifying development rows.
- The test instance was stopped and started to verify fresh tmpfs bootstrap before the final full run. Runtime connections proved vector availability, restricted privileges, tenant isolation, and pooled-context cleanup.
- Image digest recorded and pinned: `sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d`.
- Docker Desktop initially failed on an inaccessible stale `dockerInference` socket. Its two-entry runtime directory was preserved as `C:/Users/acer/AppData/Local/Docker/run.stale-codex-20261029-015022`, then Docker started successfully with a fresh runtime directory. No Docker data volume was reset. The administrator/migration/API/AI business boundaries remain as approved.
- Reviewer deferred future authentication and concurrent unrelated frontend/docs work; those are outside this approved database-only slice. The initial P1 was fixed via RED -> GREEN and the full suite is green. No remaining review findings.

Operational handoff: development stays running on localhost:55432; the disposable test container is stopped after verification. Restart it before full tests. Commands and credential/storage recovery notes are in `docs/runbooks/database.md`.
