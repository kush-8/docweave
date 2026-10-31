# Current implementation and cleanup report

DocWeave is a personal GitHub-linked documentation assistant. Core implementation and repository cleanup are present; preserved-data cutover and full release acceptance remain unfinished. Historical progress and measurements are kept only in [memory](../memory.md).

## What changed

| Area | Current result |
| --- | --- |
| Identity/API | GitHub-only sessions, direct-owner projects, immutable repository bindings, conversations/turns, consent and evidence interfaces. No workspace/member/invitation/grant/allowance or email/Google-login endpoints. |
| Project memory | Bounded SHA-pinned Python/npm metadata scanning, semantic dependency/context revisions, no-op reuse and last-good preservation on incomplete scans. |
| Knowledge/RAG | Immutable version-aware shared public catalog selections/indexes, isolated private knowledge, hybrid retrieval/RRF/reranking and validated structured answers/citations. Source-dependent waits retain query resolution and resume the original durable turn. |
| Safety/cost | Version/hash/parser/rule-bound assessments, credential blocks, owner review, current evidence authority, explicit processor consent and conservative global provider admission. Unknown paid completion does not replay automatically. |
| Frontend | API-backed login/project/chat/consent/evidence, durable progress, context notices, draft protection, accessible responsive layout and safe sign-out state. |
| Cleanup | Deleted copied legacy test application, obsolete SaaS/OIDC endpoint tests and identity/contract fixtures, unused auth/policy implementations and retired manual-workspace seed. Removed Authlib/email-validator and their exclusive transitive dependencies. Root logs live under ignored logs/development. |
| Tests | Seven current subsystem suites plus support/fixtures. Useful ingestion/retrieval/evaluation/profile regressions now use the current GitHub app and API-created personal projects; ownership and selected-scope checks replace obsolete sharing flows. Financial/preservation tests remain for actively referenced internals. |
| Documentation | PRD, architecture, rules, UI, API, tasks, runbooks and learning guides describe current behavior. Removed 19 superseded plan/runbook files; history belongs only in memory.md. |

The current-project fixture exposed a NULL-workspace source-indexing bug. Additive migration `0027_personal_source_scope` makes matching source/project workspace scopes NULL-safe while retaining exact project, selected stack, source approval and current access predicates. A source version/goal/invalidation regression covers this path.

## What did not change

- Hybrid lexical/vector algorithms, RRF/reranking and Groq LLM/Gemini embedding direction. BM25/exact worker defaults are provisional, not a release evaluation winner.
- Source/version/guardrail/consent, current owner/upstream access and global spending requirements.
- Actual development database, .env, stored artifacts, backups, vectors and ledger/unknown-operation claims: no reset or development migration was performed.
- Required Alembic migrations and retained database/financial compatibility structures. Their safe removal depends on verified data cutover, not keeping a duplicate application.
- No deployment, new paid/provider run, semantic answer cache, pricing/workspace product, sharing, webhook or repository-code ingestion.

## Verification

- Full current backend suite: **388 passed** in 114.18 seconds with warnings treated as errors.
- After dependency removal/environment sync, current API/GitHub/private-upload checks: **64 passed**.
- Frontend: **13 passed** in Chrome; production build and lint passed.
- NULL-workspace source-indexing regression passed against additive migration 0027.
- Lockfile consistency, current documentation links/encoding, removed-target checks and git diff whitespace checks passed.

Integration tests use guarded disposable PostgreSQL and mocked provider HTTP, not production accounts. The smaller suite excludes obsolete product endpoint/contract tests; current ingestion/retrieval/financial/migration checks remain. Old suite measurements are retained only in memory.md.

## Remaining tasks

The actionable [task list](../tasks.md) covers these workstreams:

1. Verified GitHub identity/ambiguous ownership mappings, backed-up restored-data rehearsal, preservation comparisons and development cutover; remove obsolete DB structures only after safe reference/data checks.
2. Actual GitHub App/installation/public-private/org/SSO/revocation verification; verified immutable profile/generation/account/pricing and private consent setup.
3. Supported pnpm/ancestor monorepo locks, force-push/concurrent/incomplete-sync cases and actionable retries; unknown-source review, explicit version-fallback acceptance and real catalog coverage states.
4. Crash/lease/restart/duplicate continuation, cancellation/deletion and changed-context wait acceptance; current access/consent/budget rechecks throughout recovery.
5. Guardrail rule-update/rescan/review/audit/recovery and dependent memory/citation invalidation; private hosted-indexing completion and cleanup/retention/backup verification.
6. Durable revision-aware summaries beyond recent 6000-token history, full agreed quality/privacy/latency/cost evaluation and truthful readiness. Readiness remains 503.
7. Semantic caching discussion after verification: measure repetition, cost and hit/false-match rates first. Compare exact/retrieval reuse; any later cache must bind owner/project/context/source/index/model/prompt/guard revisions and reauthorize every hit. No cross-user private reuse or implementation decision yet.

These are grouped acceptance workstreams, not an exhaustive edge-case checklist. Existing mocked/core tests provide partial evidence within them. No public catalog admin UI, team product or speculative infrastructure is required.

Main remaining risks are unverified live integration, preserved-data cutover and incomplete operational/release acceptance. Deterministic scanners and structural citation validation do not guarantee complete attack detection or semantic faithfulness.
