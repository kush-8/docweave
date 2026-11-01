# Personal GitHub projects

This is the active setup guide. See [tasks](../tasks.md) for remaining acceptance and [memory](../memory.md) for history.

## Setup

Use a GitHub App with Contents read-only and Metadata read-only. The web authorization flow establishes identity; installation selects repositories. Configure `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `AUTH_ENCRYPTION_KEY`, `APP_ORIGIN` and the explicit loopback-only HTTP development exception. Never put credentials in URLs, logs or browser storage.

With local Vite, use its browser origin (normally `http://127.0.0.1:5173`) and callback `/api/v1/auth/callback`; Vite forwards `/api` to backend port 58000. Organization installation/SSO approval can still be required. GitHub's selected-repository Contents permission is broader than the application's metadata-file allowlist.

Set `RAG_GENERATION_ID`, `EMBEDDING_PROFILE_ID`, `QUERY_PROFILE_ID`, `RERANK_PROFILE_ID` and optionally `ANSWER_PROFILE_ID` only to operator-verified immutable records. Configure provider keys privately. Source approval, account/capability/pricing checks, user processing consent and the shared US$20 monthly cap still apply. No workspace quotas or commercial tiers remain in the product.

Run the ingestion worker and the personal worker separately. Both use `WORKER_DATABASE_URL`; personal retrieval uses the restricted `DATABASE_URL`. Public catalog ingestion reuses existing source-fetch, parser, chunking and embedding contracts. Reviewed sources support bounded TXT/Markdown and static HTML; uploads remain TXT/Markdown.

Use Project documentation to review source/version coverage and explicitly accept broader versions. The [catalog runbook](catalog.md) documents owner decisions, operator manifest review/revocation, immutable source hashes and bounded reference catalog and version limits. These endpoints require migration `0030_documentation_review`; application startup never applies migrations automatically. Follow the migration/backup procedure before updating development.

## Preserved-data migration

Development is verified through `0038_openai_embeddings`; the authorized fresh-start and recovery migrations are complete. Current GitHub identity/session data, profiles and financial claims were preserved through the recovery upgrade. Private pre-reset and recovery backups remain under `backups/`; both actual restore rehearsals passed original-row/artifact comparisons. Recovery verification also compares canonical schema/permissions and sequences. Archived conservative charges of US$0.524697600000 still require reconciliation before paid processing is enabled. A local reset does not undo provider charges or resolve uncertain calls. The subsequent source-review cutover through 0037 also passed actual restore rehearsal and preservation checks.

The procedure below applies if older data is deliberately restored. Old-user mapping is unnecessary for the current fresh start. Do not discard retained backups or assume archived paid operations are eligible for replay.

1. Stop new requests and drain/stop both workers before backup. Do not clear stuck jobs or uncertain claims to make a check pass. Back up PostgreSQL with `pg_dump -Fc` and copy the complete artifact directory privately. Retain original backups; a fingerprint file is not a backup.
2. Capture read-only fingerprints with `docweave.preservation` using the migration role. Restore the dump/artifacts into an isolated copy with provider/GitHub credentials and workers disabled. Compare that copy against the fingerprints before migration. Never run the test suite against development or a private restored copy; tests clear only the guarded disposable service.
3. Run the ownership preflight (`python -m docweave.ownership`). Existing direct owners take precedence over old workspace memberships. Sole legacy workspace owners resolve automatically; ambiguous projects need explicit existing-user UUID mappings. `--mapping` is the original project-only read-only format, not an apply command or full-cutover readiness check.
4. Rehearse additive Alembic migrations on the restored copy. Compare original columns, artifacts, IDs, values, hashes, vectors, references and all cost/uncertainty claims. New tables are reported separately. Changed revision/profile/service rows require explicit investigation; the tool never silently ignores them. Capture a new baseline after accepting each intentional migration change.
5. Prepare the private identity manifest below. Each old user is either explicitly linked to a verified numeric GitHub identity or explicitly retained without linking. Keep operator/test/nonproject financial actors under their original UUIDs; never transfer their claims or invent GitHub accounts. Every project owner must have a verified GitHub identity before this command can apply the complete project mapping.
6. Dry-run the identity command, then rehearse `--apply` on the isolated copy. It verifies `/user` with each user token, rejects duplicate/conflicting/stale identities and owner transfers, locks application/queue tables, requires drained jobs and atomically checks every row against the exact intended changes. Only issuer/subject, previously unassigned project owners and sessions of changed identities may change. A mismatch rolls the operation back. Existing GitHub identities cannot be reassigned; email is never used to match accounts.
7. Only after actual restored-data acceptance and explicit cutover authorization, repeat backup/drain/migrate/link/verify on development. Check owner access and new login, repository-required state, preserved private knowledge, financial/unknown claims and role grants before resuming workers. Retain all legacy schema/functions until preservation-backed removal is safe.

Sole workspace owners backfill directly. Ambiguous legacy projects remain unassigned; legacy manual projects require a repository before starting new chats. Additive migrations currently reach `0028_sync_retries`; application startup never runs them automatically.

### Operator commands

From the repository root, after `uv sync --project backend --locked`, set the source environment. Supply restored migration URLs and verification tokens privately through environment variables; never paste tokens into mappings, command arguments or logs.

```powershell
$env:PYTHONPATH = (Resolve-Path backend/src).Path
uv run --project backend --locked python -m docweave.preservation --snapshot backups/before-cutover.json --artifacts storage
uv run --project backend --locked python -m docweave.preservation --compare backups/before-cutover.json --database-url-env RESTORED_MIGRATION_DATABASE_URL --artifacts backups/restored-artifacts
uv run --project backend --locked python -m docweave.ownership --database-url-env RESTORED_MIGRATION_DATABASE_URL
uv run --project backend --locked python -m docweave.ownership --identity-mapping backups/identity-map.json --database-url-env RESTORED_MIGRATION_DATABASE_URL
```

After the restored-copy prerequisites above, add `--apply` to the last command for its rehearsal. `MIGRATION_DATABASE_URL` is the default target; always use the explicit restored variable during rehearsal. Both tools require `docweave_migrator`, refuse RLS-filtered snapshots, and return safe summaries without content/tokens. Comparison exits 1 for differences and 2 for invalid inputs/access failures. File fingerprints reject missing roots, links and unreadable entries. Stop writes to both database and artifacts throughout capture/copy/comparison: a PostgreSQL snapshot cannot freeze filesystem writes. Row fingerprints do not verify schema definitions, grants, sequences or provider billing; retain the full dump and verify those separately.

The manifest format is below; replace all example IDs/subjects with inspected records. `issuer`/`subject` are the expected old identity, `github_id` is the positive integer returned by GitHub, and `token_env` names an environment variable holding that user's verification token. Tokens are used for read-only identity verification and are not stored. `retained_users` lists old nonproject/test/operator users deliberately kept under their existing identity; the internal public-catalog service is retained automatically. Unlisted legacy users block application rather than disappearing. Projects cannot be assigned to retained legacy users; resolve those records explicitly before cutover.

```json
{
  "identities": {
    "00000000-0000-4000-8000-000000000001": {
      "issuer": "https://old-login.example.invalid",
      "subject": "old-account-subject",
      "github_id": 123456,
      "token_env": "DOCWEAVE_MIGRATION_USER_TOKEN"
    }
  },
  "projects": {
    "20000000-0000-4000-8000-000000000001": "00000000-0000-4000-8000-000000000001"
  },
  "retained_users": []
}
```

Successful application preserves UUIDs, emails, artifacts, vectors, references, ledger rows and unknown claims; it revokes old sessions only for identities actually changed. Users sign in again through GitHub. Repeating the same verified manifest is safe and does not revoke newly established sessions. This tooling and disposable dump/restore tests do not establish live account mapping. The archived pre-reset database has separately passed an actual isolated restore/comparison; no old users were linked into the fresh database.

## Operational limits and recovery

- Partial/unsupported stack scans retain good memory and block the initializing chat with a safe explanation. After correcting access or metadata, use **Retry repository sync** in that chat; the API queues a durable background job and polling resumes. Duplicate retry requests reuse initializing work. No answer/provider operation is replayed.
- Supported JavaScript locks: local npm v2/v3 and pnpm lockfile 9.0, plus selected-app pnpm importers and npm v2/v3 ancestor lock paths. Ancestor traversal uses the nearest lock of each kind and rejects conflicting package managers. Only the selected app's reachable registry dependencies enter its stack, including installed npm peers. Stale importer constraints, missing required peers, overlapping installed versions, patched packages, unresolved workspace links, aliases/catalog specifiers, other pnpm versions and ancestor uv/Poetry/Yarn mappings stay incomplete. No package manager or repository code is executed.
- A turn waits only for identified required dependencies with active ingestion work. Completion wakes its original durable intent; query-resolution results are retained across a source wait. Failed, approval-blocked and capacity states must not be shown as indexing progress.
- Unknown completion is never replayed automatically. Provider claims retain conservative charges even if a response or publication acknowledgement is lost.
- The personal worker reconciles original personal/catalog jobs at startup and every 10 seconds, using worker heartbeats to recover stalled queue deliveries and application leases to fence duplicate execution. Missing deliveries are requeued in bounded batches; existing queued/running deliveries are reused. Process cancellation preserves the lease for recovery. `--once` drains work currently available and does not stay alive for future lease expiry.
- Successful provider responses have private, exact-request recovery checkpoints. Reuse rechecks upstream/job authority, current owner, profile and consent without a second charge. An uncheckpointed call, including a legacy claim without its durable stage key, blocks automatic replay even if the request changed. Reconcile such claims explicitly; never delete ledger rows to make recovery proceed. Checkpoints are recovery state, not answer evidence or a semantic cache.
- Answer publication fences changed project context and current citations. Chat deletion cancels its jobs and erases its private response checkpoints while preserving charges; late private checkpoint writes require a current owner and live leased job/conversation. Shared catalog work is not cancelled by deleting one chat. Development has the required recovery and source migrations through 0037; startup never applies migrations automatically.
- Guardrail review binds the exact document version/hash/rules. Credentials cannot be waived. Shared catalog review requires operator authority; ordinary project APIs cannot publish or mutate shared catalog content.
- Retained citations are rechecked at read/release; revocation can hide an old answer. Hybrid search does not bypass source, version, private-owner, processor or guardrail policy.

Live GitHub/provider compatibility, development migration, full release evaluation and remaining recovery/guardrail operations are intentionally not claimed by mocked/disposable verification. See the [checkpoint and remaining tasks](../reports/2026-11-01-personal-projects-checkpoint.md).
