# Current implementation and cleanup report

Operational update: use the [2026-11-03 release checkpoint](2026-11-03-release-checkpoint.md) for current migration 0041, live fixed-probe results, cleanup and evaluation preparation. The measurements below describe the earlier implementation checkpoint.

DocWeave is a personal GitHub-linked documentation assistant. Core implementation, repository cleanup and the authorized development recovery migration are complete. Accounting reconciliation, retained-schema cleanup and full release acceptance remain unfinished. Development is verified through `0038_openai_embeddings` with private restore-tested backups. Historical progress and measurements are kept only in [memory](../memory.md).

## What changed

| Area | Current result |
| --- | --- |
| Identity/API | GitHub-only sessions, direct-owner projects, immutable repository bindings, conversations/turns, consent and evidence interfaces. No workspace/member/invitation/grant/allowance or email/Google-login endpoints. |
| Project memory | Bounded SHA-pinned Python/npm/pnpm metadata scanning, selected-app npm/pnpm ancestor lock resolution, semantic dependency/context revisions, no-op reuse and last-good preservation on incomplete scans. Blocked chats retry through durable same-chat background jobs with safe progress details. |
| Knowledge/RAG | Immutable version-aware shared public catalog selections/indexes, isolated private knowledge, hybrid retrieval/RRF/reranking and validated structured answers/citations. Owner coverage decisions bind exact dependency targets; retrieval and retained public evidence share selection checks. Operator manifests stage/review/revoke public sources; source bytes are hash-pinned before parsing. Source-dependent waits retain query resolution and resume the original durable turn. |
| Safety/cost | Local LangChain scans; version/hash/parser/rule/epoch-bound assessments, durable retained-snapshot rescans, owner/operator review, safe audit/recovery and citation/summary invalidation. Current authority/policy fences protect hosted checkpoints and HTTP/idempotent release. Explicit processor consent and conservative admission remain; unknown paid completion does not replay automatically. |
| Preserved-data tooling | Migration-role-only ownership preflight respects direct owners; explicit numeric GitHub linking verifies user tokens, preserves UUIDs and checks exact transactional row changes. Read-only database/artifact fingerprints support restored-copy comparisons. Authorized migration is verified through 0037 with actual private restore rehearsals and row/artifact/schema/grant/sequence comparisons. No old-user mapping is needed for this fresh start. |
| Frontend | API-backed login/project/chat/consent/evidence, a Project documentation review panel with explicit broader-version acceptance, distinct source states and actual safe worker stages, durable progress, context notices, draft protection, accessible responsive layout and safe sign-out state. |
| Cleanup | Deleted copied legacy test application, obsolete SaaS/OIDC endpoint tests and identity/contract fixtures, unused auth/policy implementations and retired manual-workspace seed. Removed Authlib/email-validator and their exclusive transitive dependencies. Root logs live under ignored logs/development. |
| Tests | Seven current subsystem suites plus support/fixtures. Useful ingestion/retrieval/evaluation/profile regressions now use the current GitHub app and API-created personal projects; ownership and selected-scope checks replace obsolete sharing flows. Financial/preservation tests remain for actively referenced internals. |
| Documentation | PRD, architecture, rules, UI, API, tasks, runbooks and learning guides describe current behavior. Removed 19 superseded plan/runbook files; history belongs only in memory.md. |

The current-project fixture exposed a NULL-workspace source-indexing bug. Additive migration `0027_personal_source_scope` makes matching source/project workspace scopes NULL-safe while retaining exact project, selected stack, source approval and current access predicates. A source version/goal/invalidation regression covers this path.

## What did not change

- Hybrid lexical/vector algorithms, RRF/reranking and Groq LLM roles. OpenAI embeddings through LangChain are now selected; existing Gemini generations remain explicitly selectable. BM25/exact worker defaults are provisional, not a release evaluation winner.
- Source/version/guardrail/consent, current owner/upstream access and global spending requirements.
- .env and existing backups/artifact files remain retained. Fresh private backup `backups/before-reset-20261101T025020/` contains the old database and roles; its actual restore and exact row comparison passed. The development database has no old application/charge records. Archived incurred/unknown charges total US$0.524697600000 and require reconciliation before paid processing.
- Required Alembic migrations and retained database/financial compatibility structures. Their safe removal requires reference checks, not keeping a duplicate application.
- No deployment, new paid/provider run, semantic answer cache, pricing/workspace product, sharing, webhook or repository-code ingestion.

## Verification

- Focused sync backend verification: **73 passed** with warnings treated as errors. Covers bounded parser/transport behavior, owner/CSRF/deletion gates, retry deduplication, partial-memory retention, force-push pinning, serialized refresh and stale publication rejection. Additive `0029_sync_publication` protects the latter; this sync work did not apply it to development.
- Complete combined backend suite: **589 passed** in 197.59 seconds with warnings treated as errors. Covers source discovery/review, HTML parsing, private indexing/recovery, coverage/version binding, ownership/CSRF, revocation, retained citations and checked API contracts. The additional OpenAI-only routing check passes in the 13-test mocked embedding suite. The previous source integration review was clean; no new independent review was run for the embedding change.
- Worker recovery acceptance is complete, including real process kill/restart and current access/consent/budget fencing. The combined suite above includes source integration; no provider calls or charges were required.
- Preservation checks cover verified/mock identity dry-run/apply/repeat, stale/conflicting/unresolved mapping rejection, no owner transfer, session revocation, mismatch rollback, worker-drain and migration-role gates, original-column comparisons and artifact-byte drift.
- Actual `pg_dump`/`pg_restore` on the guarded disposable database preserves vector values, references and a 12-decimal uncertain charge exactly. This is synthetic test data, not a rehearsal of the actual development backup.
- Current frontend: **18 passed** in Chrome; production build and lint passed. Includes source discovery/review, explicit fallback acceptance, draft preservation and accessibility checks.
- NULL-workspace source-indexing regression passed against additive migration 0027.
- Lockfile consistency, current documentation links/encoding, removed-target checks and git diff whitespace checks passed.

Both operator command help paths and focused repository-layer checks pass. Focused sync review found no remaining actionable issues after fixing omitted npm peers, overlapping installed versions and patched pnpm handling. Unsupported formats and layouts remain incomplete; these checks do not establish live GitHub or release acceptance.

Development verification: Alembic target `0038_openai_embeddings`. Actual private backup/restore rehearsal and cutover preserve original rows/artifacts except the revision row; canonical schema/functions/grants/sequences match. All three restricted logins pass. Private evidence: `backups/openai-20261101T205444Z/acceptance.json`; scratch database removed. API/proxy liveness is 200, readiness remains 503 and anonymous identity returns 401. Paid processing remains disabled.

Integration tests use guarded disposable PostgreSQL and mocked provider HTTP, not production accounts. The smaller suite excludes obsolete product endpoint/contract tests; current ingestion/retrieval/financial/migration checks remain. Old suite measurements are retained only in memory.md.

## Remaining tasks

The actionable [task list](../tasks.md) covers these workstreams:

1. Migration is complete. Reconcile archived incurred/unknown charges before paid enablement and review retained schema references before removing obsolete structures; these remain separate acceptance tasks. Old-user mapping is unnecessary unless older data is deliberately restored.
2. Actual GitHub App/installation/public-private/org/SSO/revocation verification; verified immutable profile/generation/account/pricing and private consent setup.
3. Complete sync operational acceptance. Documentation source review/catalog is complete: explicit-consent discovery, private review/indexing and 29 entries/85 official pages verified (798 chunks; 1,707,106 normalized characters). Rolling references do not assert exact package-version compatibility; see the [catalog runbook](../runbooks/catalog.md).
4. Worker recovery acceptance and authorized development cutovers through 0037 are complete. Preserve access/consent/budget, checkpoint deletion and unknown-completion gates during guardrail work.
5. Guardrail lifecycle implementation is complete, including retained-version review, local rescans, audit/recovery and dependent memory/citation invalidation. Final serial backend suite:664 passed with warnings as errors; migration/model parity and review checks pass. Development rollout and cleanup/retention/backup verification remain separately gated; see the [guardrail runbook](../runbooks/guardrails.md).
6. Durable revision-aware summaries are implemented beyond recent 6000-token history, including policy/history invalidation. Full agreed quality/privacy/latency/cost evaluation and truthful readiness remain required. Readiness remains 503.
7. Semantic caching discussion after verification: measure repetition, cost and hit/false-match rates first. Compare exact/retrieval reuse; any later cache must bind owner/project/context/source/index/model/prompt/guard revisions and reauthorize every hit. No cross-user private reuse or implementation decision yet.

These are grouped acceptance workstreams, not an exhaustive edge-case checklist. Existing mocked/core tests provide partial evidence within them. No public catalog admin UI, team product or speculative infrastructure is required.

Main remaining risks are unverified live integration, archived accounting reconciliation and incomplete operational/release acceptance. Deterministic scanners and structural citation validation do not guarantee complete attack detection or semantic faithfulness.

Provider setup: `text-embedding-3-small` uses LangChain at 768 dimensions for embedding only. Its key can read model metadata (HTTP 200), and funded OpenAI credits are visible. Migration0038 passed actual dump/restore rehearsal and preservation checks. All local profile IDs are configured, including disabled Groq GPT-OSS 20B query/reranking and GPT-OSS 120B generation profiles. Groq Inference APIs ZDR is enabled. Personal repository access is the agreed scope; organization/SSO is excluded. The user authorized five fixed synthetic checks up to US$0.01 and private processing for SwapKr only, conditional on verification and billing gates passing. No provider calls, effective consent or activation have occurred. API/proxy liveness is 200; readiness remains 503. The focused 13-test mocked embedding suite passes. Final archived billing reconciliation, live capability/account verification and activation keep this task in progress. Private setup/approval evidence is under `backups/live-setup-20261101T210659Z/`.
