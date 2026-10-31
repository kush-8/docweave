# Database operations

Use PostgreSQL/pgvector via Docker Compose. `db` is persistent development on `127.0.0.1:55432/docweave`; `test-db` is disposable tmpfs on `127.0.0.1:55433/docweave_test`. API runtime, worker and migrator use distinct roles/URLs. Runtime has no general write, role-switch or RLS-bypass authority; domain mutations use narrow fixed-search-path functions. Keep transaction-local actor scope parameter-bound and derived from verified identity.

Preserve an existing `.env`, database volume, private storage, backups and ledger. For a new environment only, copy `.env.example` and privately replace every password/key placeholder, keeping role passwords and URLs consistent. Bootstrap runs only on empty storage; changing environment passwords does not rotate existing roles. Never recreate development storage to fix login errors.

## Verification environment

```powershell
uv sync --project backend --locked
docker compose config --quiet
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests -q -W error
```

Run database suites serially. Fixtures migrate/clear only the guarded local test service. Startup does not run migrations. Code migration head is `0027_personal_source_scope`; this does not describe the revision of an uninspected development database.

## Existing-data cutover

Follow [personal setup/preservation](personal-projects.md#preserved-data-migration): read-only ownership preflight, verified numeric GitHub identity linking, explicit ambiguous ownership, backup, isolated restore/rehearsal, count/reference/hash/vector/ledger comparisons, drain/migrate/resume. Migrations keep previous user UUIDs and operation identities; do not merge financial hashes or turn uploads into public catalog entries. Keep historical Alembic migrations and currently referenced schema/functions until safe removal is proved. No development migration/reset is part of source cleanup.

Recovery scripts under `backend/infra/postgres/` are explicit operator tools, not startup steps. Supply credentials privately, never as logged command values. Verify narrow role grants after recovery. See [tasks](../tasks.md) for outstanding rehearsal, cleanup/retention and readiness acceptance.
