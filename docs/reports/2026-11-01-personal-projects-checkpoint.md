# Personal projects: implementation and cleanup checkpoint

2026-11-01. This completes the current implementation/verification and repository-cleanup checkpoint requested by the user. It does **not** mark the entire personal-project refactor or release complete.

## What changed

| Area | Current result |
| --- | --- |
| Identity/API | Default application is GitHub-only. Direct-owner project, repository binding, conversation, turn, processing-policy and evidence endpoints are wired. No workspace/member/invitation/grant or email/Google-login routes are mounted. |
| Project context | Bounded commit-pinned Python/npm metadata scanning; stable dependency identities and semantic revisions; no-op commits avoid reembedding. New-chat checks use serialized durable jobs; incomplete scans retain good memory. |
| Documentation | Immutable public catalog revisions, private project selections, shared preparation/index publication and deduplicated ingestion. Ready public indexes are reused; private knowledge is separately scoped. |
| RAG/turns | Personal hybrid retrieval, RRF/reranking, structured generation and validated retained citations are wired through admitted provider calls. Required-source waits resume the same durable turn without repeating completed query resolution. |
| Guardrails/cost | Content/version/rule-bound assessments, quarantine/review, nonwaivable credential blocks, incoming/output checks, exact evidence membership, release reauthorization, consent and global conservative admission are enforced on the new path. Unknown paid completion is never automatically replayed. |
| Frontend | Real API-backed GitHub/project/chat setup, processing permissions, durable status/evidence views, latest-context notice, draft protection, safe sign-out and no persistent private browser storage. |

Provider HTTP is mocked in end-to-end tests. This is code/runtime-boundary evidence, not proof that a real GitHub installation or hosted account is configured and eligible.

## What was cleaned up

- Moved 13 root execution logs into ignored `logs/development/`; preserved their evidence rather than deleting it.
- Organized 47 backend test/smoke modules into `api`, `database`, `github`, `personal`, `rag`, `providers`, `evaluation` and `legacy`. Imports use packages and stable `tests.paths`; all 650 tests remain discoverable.
- Organized frontend tests into `e2e`, `architecture` and `support`.
- Moved obsolete SaaS/OIDC application routes and their exclusive schema/repository/configuration helpers out of production into legacy regression fixtures. Historical contracts and identity configuration remain test inputs, not product endpoints/services.
- Removed Keycloak/Mailpit services from active Compose and their settings from `.env.example`. Authlib and email validation are development-only dependencies; package versions did not change.
- Removed the unused synthetic conversation/evidence components and superseded placeholder files. Kept fixture licenses and useful historical evaluation evidence.
- Updated current setup/testing documentation and marked retired identity/workspace runbooks historical.

## What did not change

- Search remains hybrid; native full-text/BM25, exact/HNSW, fusion and reranking implementations remain available. Personal-worker BM25/exact defaults are provisional, not a newly established evaluation winner.
- Groq LLM roles and Gemini embeddings remain the provider direction. API keys do not bypass account/capability/pricing, private-processing consent or source policy.
- Existing development database, `.env`, stored artifacts, backups, vectors, cost history and uncertain operation claims were not reset or migrated in this task. Legacy schema/functions remain for preservation-backed migration coverage.
- Historical paid-pilot reports remain historical; no new paid/provider run or deployment occurred. Full release answer-quality evidence is not claimed.
- Semantic answer caching, a new vector database/queue, webhooks, pricing tiers and team sharing were not added.

## Verification

- Final serial backend suite: **650 passed** in 281.16 seconds, with warnings treated as errors (`pytest backend/tests -q -W error`). Guarded disposable PostgreSQL only.
- Final frontend suite: **13 passed** in Chrome, including architecture, responsive and accessibility checks.
- Frontend production build and lint passed after test relocation.
- Lockfile consistency, simplified Compose configuration, active documentation links and `git diff --check` passed.
- Focused real-PostgreSQL tests exercise owner isolation, OAuth/session refresh, scope constraints, shared hybrid retrieval, credential revocation, private upload/review, conservative admission and complete RAG/wait-resume with mocked provider HTTP.
- Cleanup review and follow-up found no actionable production/fixture import or relocation regressions.

These checks do not establish live GitHub/provider compatibility, full release answer quality or development-data migration safety.

## Remaining tasks, in order

These are grouped workstreams, not an exhaustive implementation checklist. The acceptance cases below remain to be completed or verified; passing the current test suite does not establish that every approved behavior is finished.

1. **Preserved-data cutover:** finish explicit existing-user-to-verified-GitHub identity mapping and ambiguous owner application; back up and rehearse on an isolated restored development copy; compare IDs, hashes, vectors and ledger claims; then drain/migrate/resume. Remove remaining legacy database structures only after this preservation gate.
2. **Real integration setup:** configure the actual GitHub App/callback/installations and verify public/private repository access and revocation. Configure verified immutable RAG profiles/generation and actual processing consent; perform only separately authorized live provider checks.
3. **Complete supported scan/document setup:** add pnpm and supported ancestor monorepo lock mappings; finish unknown-source/version-fallback review and actual catalog coverage. Current bounded TXT/Markdown ingestion and explicit unsupported/partial states must remain honest.
4. **Finish operational recovery and guardrail coverage:** exercise process crash/lease/cancellation and expired-session scenarios, public catalog review/rescan/retry and all consent/revocation changes. Complete the remaining guardrail audit/rule-update workflow and private hosted-indexing integration; do not equate basic assessment persistence with the entire approved guardrail milestone.
5. **Finish conversation/release evidence:** implement durable summaries beyond the current bounded recent-history input, run the full agreed answer/citation/abstention/privacy/latency/cost evaluation, and complete release readiness. `/health/ready` intentionally remains 503.
6. **Discuss semantic caching:** first measure repeated-question frequency, latency, cost and likely hit rate. Compare exact-request/retrieval reuse with semantic answer caching. Any later cache must bind owner/project, conversation context, stack/source/index/model/prompt/guardrail revisions and reauthorize citations on every hit. No cross-user private answer reuse; no cache implementation is approved by this checkpoint.

### Acceptance details within those workstreams

- GitHub setup: installation/setup status, organization/SSO and denied-installation cases, expired sessions, refresh races and upstream revocation; distinguish mocked regression coverage from real-account verification.
- Catalog and scans: actionable sync retry, supported ancestor locks/monorepos, force pushes and concurrent new chats; unknown-source approval, explicit version-fallback acceptance and accurate coverage/failure/capacity states. pnpm is an additional supported-parser task, not a reason to claim existing conservative scans complete for every repository.
- Durable workers: verify crash/lease recovery, restart reconciliation, one continuation under duplicate delivery, cancellation/deletion, changed context/dependency requirements during waits and reauthorization before continuation. Existing happy-path/wait-resume tests are partial evidence for this wider matrix.
- Guardrails and memory: rule-update invalidation/rescans, shared versus private review authority, audit/recovery procedures, dependent summary/citation invalidation and durable summaries rebuilt against context revisions.
- Release and preservation: map ambiguous/nonproject records explicitly, preserve UUIDs and uncertain operation identities, restore/rehearse/compare before development cutover, then remove obsolete structures; finish readiness, failure/recovery and agreed quality/privacy/latency/cost evidence.
- Documentation: consolidate the retained historical PRD/architecture/API/design/rules/task bodies into a coherent current specification, preserving relevant acceptance requirements and historical evidence. Current top-level notices/report/runbook take precedence in the meantime. The approved plan's coarse unchecked milestones represent incomplete acceptance, not absence of all implementation.

Pricing/workspaces/sharing, push webhooks, repository-code ingestion, established-project repository rebinding and a public catalog administration UI remain deliberately omitted. Operator review capability does not require adding that omitted UI. Semantic caching requires discussion before any implementation decision.

Main remaining risk: live identity/provider behavior and preserved-data cutover are unverified, even though the core path is exercised on controlled disposable inputs. Deterministic guardrails and structural citation checks do not guarantee complete detection or semantic truth.
