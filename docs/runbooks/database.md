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

Run database suites serially, including runs from other chats. Fixtures migrate/clear only the guarded local test service. Startup does not run migrations. Development is verified at `0044_retire_product_rpcs`. Each private dump was restored and rehearsed before upgrading the original. 0043proved the two retired tables empty and recorded them separately;0044removed only thirteen orphan routines. All retained rows/artifacts and canonical schema/functions/grants/sequences match their accepted rehearsals. All three restricted logins pass. Live GitHub identity/session data and all six synthetic financial claims were preserved. Current evidence is private under `backups/retired-rpcs-20261103T024949Z/`; API/proxy liveness200 and readiness503. See [retention](retention.md) for backup expiry, external-journal restore replay and outstanding deployed acceptance.

## Existing-data cutover

The authorized fresh start has a private database/role/artifact backup in `backups/before-reset-20261101T025020/`, verified by isolated restore and exact comparison of 32 original application/queue tables. Old local records are cleared; archived incurred/unknown charges remain held unresolved and must not be replayed or inferred settled. The six synthetic compatibility calls had separate bounded authority; any further paid workload requires its own authority. Retired Keycloak storage and the disposable test database were not reset.

If older data is deliberately restored, follow [personal setup/preservation](personal-projects.md#preserved-data-migration): read-only ownership preflight, verified numeric GitHub identity linking, explicit ambiguous ownership, backup, isolated restore/rehearsal, count/reference/hash/vector/ledger comparisons, drain/migrate/resume. Migrations keep previous user UUIDs and operation identities; do not merge financial hashes or turn uploads into public catalog entries. Keep historical Alembic migrations and currently referenced schema/functions until safe removal is proved.

`python -m docweave.preservation --snapshot <private-file>` captures read-only database/artifact fingerprints; `--compare <private-file>` checks a restored copy, including original columns across additive migrations. Select that copy with `--database-url-env RESTORED_MIGRATION_DATABASE_URL` and `--artifacts <restored-directory>`. This creates comparison evidence, not a backup. The [personal runbook](personal-projects.md#operator-commands) documents private identity manifests, worker drain and explicit `docweave.ownership --apply` for a future deliberate restore.

0043 refuses nonempty retired invitation/request tables and unexpected direct consumers. Downgrade recreates their empty historical schemas/functions/grants. A baseline containing a retired table is still rejected by the general preservation checker; do not weaken that check. The accepted0043cutover separately recorded both zero-row baselines, proved the original dump restored exactly, then compared every retained table/artifact against a baseline excluding only those two explicitly retired empty tables. Old backups with records require deliberate preservation before upgrade. Keep the latest external deletion journal independently and replay it before serving any restored data; see [restore procedure](retention.md).

0044 removes the remaining orphan workspace/member/manual-policy RPCs and unused assessment alias, with installed caller/body guards and exact downgrade contracts. Their tables and current personal policy/version-bound review methods remain. Compatibility/public financial tools and ownership preservation do not depend on those old entry points. See [complete RPC audit](../reports/2026-11-03-retired-product-rpcs.md).

Recovery scripts under `backend/infra/postgres/` are explicit operator tools, not startup steps. Supply credentials privately, never as logged command values. Verify narrow role grants after recovery. See [tasks](../tasks.md) for outstanding rehearsal, cleanup/retention and readiness acceptance.
