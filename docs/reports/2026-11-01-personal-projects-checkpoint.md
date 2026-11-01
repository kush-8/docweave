# Current implementation and cleanup report

DocWeave is a personal GitHub-linked documentation assistant. Core implementation, repository cleanup and the fresh-start database migration are complete. Accounting reconciliation, retained-schema cleanup and full release acceptance remain unfinished. Development is at `0028_sync_retries` with a verified private backup of old data. Historical progress and measurements are kept only in [memory](../memory.md).

## What changed

| Area | Current result |
| --- | --- |
| Identity/API | GitHub-only sessions, direct-owner projects, immutable repository bindings, conversations/turns, consent and evidence interfaces. No workspace/member/invitation/grant/allowance or email/Google-login endpoints. |
| Project memory | Bounded SHA-pinned Python/npm/pnpm metadata scanning, selected-app npm/pnpm ancestor lock resolution, semantic dependency/context revisions, no-op reuse and last-good preservation on incomplete scans. Blocked chats retry through durable same-chat background jobs with safe progress details. |
| Knowledge/RAG | Immutable version-aware shared public catalog selections/indexes, isolated private knowledge, hybrid retrieval/RRF/reranking and validated structured answers/citations. Owner coverage decisions bind exact dependency targets; retrieval and retained public evidence share selection checks. Operator manifests stage/review/revoke public sources; source bytes are hash-pinned before parsing. Source-dependent waits retain query resolution and resume the original durable turn. |
| Safety/cost | Version/hash/parser/rule-bound assessments, credential blocks, owner review, current evidence authority, explicit processor consent and conservative global provider admission. Unknown paid completion does not replay automatically. |
| Preserved-data tooling | Migration-role-only ownership preflight respects direct owners; explicit numeric GitHub linking verifies user tokens, preserves UUIDs and checks exact transactional row changes. Read-only database/artifact fingerprints support restored-copy comparisons. Fresh-start migration is complete at 0028; actual old-data backup restoration and 32-table comparison passed and backup hashes are verified. No old-user mapping is needed for this fresh start. |
| Frontend | API-backed login/project/chat/consent/evidence, a Project documentation review panel with explicit broader-version acceptance, distinct source states and actual safe worker stages, durable progress, context notices, draft protection, accessible responsive layout and safe sign-out state. |
| Cleanup | Deleted copied legacy test application, obsolete SaaS/OIDC endpoint tests and identity/contract fixtures, unused auth/policy implementations and retired manual-workspace seed. Removed Authlib/email-validator and their exclusive transitive dependencies. Root logs live under ignored logs/development. |
| Tests | Seven current subsystem suites plus support/fixtures. Useful ingestion/retrieval/evaluation/profile regressions now use the current GitHub app and API-created personal projects; ownership and selected-scope checks replace obsolete sharing flows. Financial/preservation tests remain for actively referenced internals. |
| Documentation | PRD, architecture, rules, UI, API, tasks, runbooks and learning guides describe current behavior. Removed 19 superseded plan/runbook files; history belongs only in memory.md. |

The current-project fixture exposed a NULL-workspace source-indexing bug. Additive migration `0027_personal_source_scope` makes matching source/project workspace scopes NULL-safe while retaining exact project, selected stack, source approval and current access predicates. A source version/goal/invalidation regression covers this path.

## What did not change

- Hybrid lexical/vector algorithms, RRF/reranking and Groq LLM/Gemini embedding direction. BM25/exact worker defaults are provisional, not a release evaluation winner.
- Source/version/guardrail/consent, current owner/upstream access and global spending requirements.
- .env and existing backups/artifact files remain retained. Fresh private backup `backups/before-reset-20261101T025020/` contains the old database and roles; its actual restore and exact row comparison passed. The development database has no old application/charge records. Archived incurred/unknown charges total US$0.524697600000 and require reconciliation before paid processing.
- Required Alembic migrations and retained database/financial compatibility structures. Their safe removal requires reference checks, not keeping a duplicate application.
- No deployment, new paid/provider run, semantic answer cache, pricing/workspace product, sharing, webhook or repository-code ingestion.

## Verification

- Focused sync backend verification: **73 passed** with warnings treated as errors. Covers bounded parser/transport behavior, owner/CSRF/deletion gates, retry deduplication, partial-memory retention, force-push pinning, serialized refresh and stale publication rejection. Additive `0029_sync_publication` protects the latter; this sync work did not apply it to development.
- Documentation API/SQL checks: **9 passed**, including explicit fallback acceptance, target changes, ownership/CSRF, source removal, operator revocation and retained-citation fencing. The checked API contract includes the coverage/selection routes. Coordinated combined backend run with recovery: **469 passed** in 141.70 seconds with warnings treated as errors. Later catalog/source additions require their own verification.
- Worker recovery: startup/10-second bounded reconciliation, stalled-queue recovery, cancellation-safe leases, duplicate fencing and private exact-response checkpoints are implemented. Unknown stages cannot be replayed after request changes. Context checks fence late answers; chat deletion erases private checkpoints and prevents late writes, retaining charges. Guarded disposable Alembic model/schema check reports no new upgrade operations. Independent review stopped at a usage limit; manual review completed. Fresh review and live process-kill/restart acceptance remain open. Migrations 0031–0033 were not applied to development by this task.
- Preservation checks cover verified/mock identity dry-run/apply/repeat, stale/conflicting/unresolved mapping rejection, no owner transfer, session revocation, mismatch rollback, worker-drain and migration-role gates, original-column comparisons and artifact-byte drift.
- Actual `pg_dump`/`pg_restore` on the guarded disposable database preserves vector values, references and a 12-decimal uncertain charge exactly. This is synthetic test data, not a rehearsal of the actual development backup.
- Current frontend: **17 passed** in Chrome, including documentation review, explicit fallback acceptance, safe worker stages, draft preservation and accessibility checks; production build and lint passed.
- NULL-workspace source-indexing regression passed against additive migration 0027.
- Lockfile consistency, current documentation links/encoding, removed-target checks and git diff whitespace checks passed.

Both operator command help paths and focused repository-layer checks pass. Focused sync review found no remaining actionable issues after fixing omitted npm peers, overlapping installed versions and patched pnpm handling. Unsupported formats and layouts remain incomplete; these checks do not establish live GitHub or release acceptance.

Fresh development verification: Alembic head `0028_sync_retries`; `alembic check` reports no new upgrade operations; 20 old-data tables and the queue are empty; only the built-in public-catalog service identity remains. Migrator/runtime/worker logins retain restricted role flags. The original backup hashes match. The 0028 upgrade preserves all original-column row fingerprints except the expected Alembic revision change; artifacts are unchanged. Focused retry/preservation/identity checks: **23 passed** with warnings as errors. The temporary restore database is removed. No hosted/GitHub processing was dispatched by migration.

Integration tests use guarded disposable PostgreSQL and mocked provider HTTP, not production accounts. The smaller suite excludes obsolete product endpoint/contract tests; current ingestion/retrieval/financial/migration checks remain. Old suite measurements are retained only in memory.md.

## Remaining tasks

The actionable [task list](../tasks.md) covers these workstreams:

1. Migration is complete. Reconcile archived incurred/unknown charges before paid enablement and review retained schema references before removing obsolete structures; these remain separate acceptance tasks. Old-user mapping is unnecessary unless older data is deliberately restored.
2. Actual GitHub App/installation/public-private/org/SSO/revocation verification; verified immutable profile/generation/account/pricing and private consent setup.
3. Complete sync operational acceptance and expand/verify catalog coverage. Owner fallback/coverage decisions and operator manifest review are implemented, with three bounded publisher-page examples. Publisher-linked discovery, private unknown-source review and all 29 required catalog entries remain open; see the [catalog runbook](../runbooks/catalog.md).
4. Recovery implementation passes the coordinated backend suite. Complete fresh independent review and live process-kill/restart acceptance; migrate development separately when authorized. Keep current access/consent/budget and unknown-completion gates throughout recovery.
5. Guardrail rule-update/rescan/review/audit/recovery and dependent memory/citation invalidation; private hosted-indexing completion and cleanup/retention/backup verification.
6. Durable revision-aware summaries beyond recent 6000-token history, full agreed quality/privacy/latency/cost evaluation and truthful readiness. Readiness remains 503.
7. Semantic caching discussion after verification: measure repetition, cost and hit/false-match rates first. Compare exact/retrieval reuse; any later cache must bind owner/project/context/source/index/model/prompt/guard revisions and reauthorize every hit. No cross-user private reuse or implementation decision yet.

These are grouped acceptance workstreams, not an exhaustive edge-case checklist. Existing mocked/core tests provide partial evidence within them. No public catalog admin UI, team product or speculative infrastructure is required.

Main remaining risks are unverified live integration, archived accounting reconciliation and incomplete operational/release acceptance. Deterministic scanners and structural citation validation do not guarantee complete attack detection or semantic faithfulness.
