# Task 3A — durable bounded text ingestion

Scope: backend only on the user-selected main branch; preserve the pre-existing uncommitted budget/planning slice. No paid calls, frontend, retrieval indexes or source discovery.

Reach: upload/document/version/source/job routes; existing collection authority and pagination; private artifact storage; immutable documentation selections; Alembic/models; Procrastinate ingestion queue and restricted worker login; isolated text parser; synthetic and frozen official fixtures; runtime/draft contracts and runbooks.

## Execution ledger

- Read tasks 3A, PRD, architecture, rules and current authority/migration/test patterns. TDD and executing-plans guide implementation inline; fresh review follows verification.
- Ruling: one explicitly selected TXT/Markdown page per immutable documentation selection in 3A. No crawling or HTML parsing; broader formats/source coverage remain Task 8. Version coverage is explicit, including rolling FastAPI snapshots.
- Ruling: local snapshot preparation can complete without hosted inference; document status remains awaiting_approval or waiting_capacity. No fake transport is shipped as a production provider or represented as semantic indexing. Test transports exercise the same authorization boundary.
- Ruling: private generated artifacts precede DB references; known rejected transactions remove new artifacts, while uncertain commit acknowledgements retain potentially referenced bytes for reconciliation. Queue insertion shares the metadata transaction via Procrastinate's SQL deferral function, serving as the transactional outbox. Cost if wrong: storage use until reconciliation; deleting uncertain bytes would risk permanent snapshot loss.
- User decision 2026-10-31: operator-only seed SQL now; owner source approval API stays Task 7. Seed reruns retain revocation.
- User decision 2026-10-31: Task 3B uses SQL BM25 with statistics over only the authorized corpus; no search extension/image change.

## Checkpoints

- [x] RED: initial 6 parser failures and 8 missing-module fixture errors; 21 source failures; later missing worker/fixture failures and targeted review regressions.
- [x] GREEN: storage, parsing, migration/models, transactional queue, APIs and worker recovery.
- [x] Verification: restricted logins, post-wait revocation/deletion, stale-worker fencing, schema comparison/downgrade, full backend suite, contracts and whitespace. Final full suite: **476 passed**, warnings as errors. Lockfile/Compose/whitespace checks passed.
- [x] Fresh read-only review completed. All five material findings fixed through observed failing regressions; the final full suite passed. No deferred minor findings.
- [x] Runbook, public contracts, status and handoff updated. No persistent development migration, paid calls, frontend changes, commit/push or deployment.

Local-preparation checkpoint complete. Remaining embedding-specific 3A proof is exercised with 3B's fake/recorded scoped indexing; no production embedding transport was added here. The overall Task 3 remains open.

No existing changes will be committed together with this slice without separating ownership. Development DB credentials/volumes remain untouched.
