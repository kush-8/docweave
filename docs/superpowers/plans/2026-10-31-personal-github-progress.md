# Personal GitHub refactor execution ledger

Plan: [approved design](2026-10-31-personal-github-projects.md). Latest user direction: finish the current implementation/verification checkpoint, clean repository files/logs/test organization, then list remaining tasks. Do not represent the entire refactor as finished.

## Current checkpoint — 2026-11-01

The default application is personal/GitHub-only; legacy SaaS/OIDC handlers and their exclusive helpers now live in backend/tests/legacy/app rather than production. Old identity services are removed from current Compose. Actual .env, development data, storage, backups and charge history were not changed/reset. Authlib/email-validator moved to dev dependencies, with unchanged versions.

Additive migrations 0013–0026 implement owner/repository state, public catalog scopes, durable conversations/jobs/waits, guard assessment/review/release, global provider admission and source-wait resolution reuse. These migrations have run only against guarded disposable PostgreSQL, not development.

Core paths have real-DB/mocked-HTTP coverage: GitHub sessions, personal HTTP/upload review, shared hybrid retrieval and unlink/revocation, full personal resolution→embedding→fusion/reranking→answer/citation, and same-turn waiting/resume without a second query-resolution call. The old algorithms/providers/evaluation history remain; live account compatibility and full release quality do not follow from these tests.

Cleanup: 13 root logs moved to ignored logs/development, 47 backend test/smoke modules grouped into eight packages, frontend specs grouped into e2e/architecture/support, old preview files and superseded placeholders removed. Stable path/import updates retain 650 collected tests. Current README, runbook and test guides describe the new layout.

Verification before final rerun: full suite found four issues (nullable legacy grant metadata, service-row count assertion, explicit scope check SQLSTATE, and ready-index reuse expectation). All six focused cases passed after fixes. Subsequent current API+legacy regressions passed 339 tests. Frontend build/lint and 13 Chrome/accessibility checks passed before relocation; final post-cleanup suites have now passed. Lock/Compose checks pass. Fresh cleanup review and its follow-up found no actionable production/fixture import or relocation regressions. The final post-move frontend run passed all 13 Chrome/accessibility/architecture tests; build and lint passed again. Final serial backend suite passed all 650 tests in 281.16 seconds with warnings treated as errors; no development database was used.

## Rulings

- Preserve legacy database structures and historical tests until a restored-data cutover proves safe removal; no synthetic workspace replaces direct ownership.
- Source-dependent loading requires identified required targets and active jobs; retrieval confidence alone is insufficient.
- Use operator-verified explicit provider/generation configuration; no unverified private dispatch or paid compatibility run is implied by implementation authorization.
- Keep unsupported pnpm/ancestor lock metadata explicit and preserve last good memory; do not guess a complete stack.
- User's current checkpoint instruction bounds this turn; full remaining work is recorded in the report rather than silently marked complete.

## Remaining work

See the [checkpoint report](../../reports/2026-11-01-personal-projects-checkpoint.md) for the ordered list: preserved-data/identity cutover, live integration setup, scan/catalog/review completion, recovery/guardrail/private-index completion, summaries/full release evaluation/readiness, then semantic-cache discussion. No deployment, paid inference or development migration was performed.
