# Bounded text ingestion

Task 3A implements TXT/Markdown upload, replacement, document/version listing, approved single-page source import/refresh, document/source deletion and safe job listing/status. It prepares immutable local snapshots and exact character/line locators. It does not create retrieval indexes or make embedding/LLM calls. A preparation job can be `completed` at `snapshot_published` while its document is `awaiting_approval` or `waiting_capacity`; this does not mean it is searchable. Readiness remains 503.

## Setup

Use `uv sync --project backend --locked`. The pinned Procrastinate 3.10.0 schema belongs to `queue`; application models belong to `app`. Bootstrap now requires a distinct `PG_WORKER_PASSWORD`, creates `docweave_worker` and the migration-owned `queue` schema, and grants the worker only queue access plus narrow ingestion functions. `docweave_runtime` cannot read queue internals, raw version records or perform general document DML. Queue payloads contain only job IDs.

For a fresh database, configure `.env` from `.env.example` before bootstrap. For an existing database, an administrator must create the restricted worker login, grant its database connection/app schema usage and create the migration-owned `queue` schema before applying `0008_ingestion`; changing bootstrap does not change existing roles. Keep the worker password out of shell history and command output. Do not reset a development volume or change existing role passwords to satisfy this setup. This session migrated only the guarded disposable service; development credentials still need restoration.

Build the isolated parser from the repository root:

```powershell
docker build -t docweave-text-parser:3a -f backend/infra/parser/Dockerfile backend
```

The Dockerfile pins its Python image digest. Each parse starts a nonroot container with no network or mounts, read-only root, dropped capabilities, no new privileges, 512 MiB memory, one CPU, 16 processes, bounded tmpfs and a 60-second supervisor deadline. Only document bytes enter stdin; no database/provider secrets or private storage enter the container. A trusted worker needs access to Docker to supervise it. Parser/cleanup timeouts are transient failures, not successful preparation.

Configure `WORKER_DATABASE_URL` for the worker login and `INGESTION_STORAGE_ROOT` for a private directory shared by API and worker, outside static/public serving. The default is the ignored repository `storage/` directory. Generated UUID filenames are internal and never returned over HTTP. Storage availability and permissions remain operator responsibilities; the machine administrator is outside the application-isolation threat model.

```powershell
uv run --project backend --locked python -m docweave.worker
# Process currently available jobs and exit:
uv run --project backend --locked python -m docweave.worker --once
```

Windows uses a Selector event loop because Psycopg's async connector requires it. Container subprocess supervision runs in a thread, so this does not depend on Selector subprocess support. Procrastinate uses the separate `ingestion` queue, concurrency one and a shared lock. A database advisory lock also excludes direct duplicate execution. Domain leases have fresh fencing tokens and expire after 120 seconds; publication rechecks expiry and current policy after workspace-lock waits. Recovery checks stalled worker heartbeats and expired domain leases. Transient preparation gets at most three attempts; invalid content/policy failures do not retry automatically. There are no paid operations to replay in this slice.

## Upload and inspect

Authenticated mutations require the existing same-origin/session CSRF headers. POST one multipart field named `file` to `/api/v1/collections/{id}/documents`; use `/api/v1/documents/{id}/versions` for replacement. Supported filename/media pairs are `.txt`/`text/plain` and `.md` or `.markdown`/`text/markdown`. Reject path-like names, extra fields/files, empty or oversized bodies. Documents enter quarantine before parsing. Malware scanning is explicitly `disabled`; this does not claim a malware scan. PDF/DOCX and configured scanner integration remain Task 8.

Bounds: 20 MiB upload, two million decoded characters, 10,000 chunks per document, strict UTF-8, no binary controls except tab/newline. Normalize BOM/CRLF/CR to UTF-8/LF before hashing. Chunking uses provisional 350 whitespace units, preserving heading boundaries and small fenced blocks; oversized blocks use a 50-unit overlap. Exact offsets always refer to the captured normalized text. These units are not verified model tokens: 3C must enforce the real embedding tokenizer/limits before external calls.

Accepted uploads return 202 with document/job IDs, status URL and request ID. Poll `/api/v1/jobs/{id}`; use `/api/v1/projects/{id}/jobs`, `/collections/{id}/documents`, `/documents/{id}` and `/documents/{id}/versions` for authorized metadata. Pagination is actor/resource-bound, 25 by default and at most 100. Raw bytes, filesystem paths and source hashes are not public fields.

Document/job insertion and Procrastinate deferral share one transaction: the queue row is the transactional outbox. Artifacts are written before their references. A known rejected transaction removes new bytes; uncertain commit acknowledgements preserve potentially referenced bytes. Reconciliation removes unreferenced generated artifacts after five minutes, avoiding in-flight artifacts. Periodic worker maintenance performs this reconciliation. Deletion first commits tombstones/fences and removes access, then erases referenced files; maintenance catches missed file deletion after a crash. Preserve DB tombstones when backing up/restoring; the full restore/backup-retention drills remain Task 11.

Version identity is document + normalized hash + parser configuration, including media type. Duplicate delivery does not create another snapshot. Explicit A→B→A replacement reactivates the retained immutable A snapshot under current authority. Failed replacement preserves the last good active snapshot and marks it stale. Superseded snapshots have no implicit expiry. Re-indexing/explicit job-retry APIs remain reserved for later lifecycle work.

## Operator-approved sources

The user chose operator-only seed SQL on 2026-10-31; the owner-facing approval API remains Task 7. Review the exact origin/path/version and attribution before executing [pilot-text-selections.sql](../../backend/catalog/pilot-text-selections.sql) as the migration login, passing psql variables `workspace_id`, `project_id`, `approved_by` and `ON_ERROR_STOP=1`. It verifies current workspace ownership and the project, and seeds a commit-pinned FastAPI Markdown page with rolling coverage. Reruns do not restore revoked approval. This is a scoped pilot approval, not global catalog verification.

POST `/api/v1/projects/{id}/sources` with `source_selection_id` and `collection_id`. Only stored, active selections belonging to that project/workspace are accepted; client URLs/trust assertions are rejected. New sources have one explicitly selected page. A selection is immutable apart from its active flag. A migration-role operator can revoke it with a parameterized `UPDATE app.documentation_selections SET active=false WHERE id=...`; workers recheck before fetch/processing/publication. Refresh uses `/api/v1/sources/{id}/refresh`. Delete tombstones the source/document; repeated import cannot undo that deletion.

The fetcher allows HTTPS standard port only, no credentials, queries, fragments, encoded/ambiguous paths or redirects outside the approved origin/path prefix. Every resolved address must be public unicast and nonreserved; the socket connects to that validated address while TLS verifies the original hostname. It does not inherit proxy settings, cookies, GitHub tokens or authorization headers. Every request waits at least one second, has a ten-second deadline, rejects compression and accepts at most two MiB. Check `/robots.txt` first; denial, unverifiable redirects/status or excessive crawl delay fail closed. At most three redirects and one page per selection are supported. HTML/crawling/full-catalog coverage remain Task 8.

The [fixture manifest](../../backend/tests/fixtures/ingestion/manifest.json) freezes a synthetic FastAPI→PostgreSQL runbook, commit-pinned rolling FastAPI Markdown and extracted PostgreSQL 17 documentation text, with hashes/attribution/transformation. PostgreSQL's captured HTML is converted to TXT only for the frozen fixture; this is not a live HTML adapter. FastAPI Markdown includes literal upstream template/include directives and does not establish exact package-version coverage. These are deterministic ingestion inputs, not semantic quality results.

## Verification and failure walkthrough

Start only the guarded disposable service, build the parser, then run:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests -q -W error
```

Tests exercise real restricted logins/migrations, queue deferral/drain/crash recovery, current read/write grants, post-wait authority, source revocation, deletion during parsing, lease fencing/expiry, timeout recovery, exact retained spans, media changes, A→B→A replacement, uncertain commit acknowledgements and artifact reconciliation. A process-level CLI test proves a custom private storage directory works. No paid keys are used.

One failure: replacement B previously caused a later A replacement to return A's old completed job, leaving B active. The regression now observes that failure first; replacement queues a fresh publication intent, and snapshot uniqueness reuses A's existing immutable version. Another regression confirms that losing a publication acknowledgement cannot erase bytes already referenced by a committed version.
