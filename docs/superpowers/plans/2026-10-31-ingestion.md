# Task 3A — durable bounded text ingestion

Scope: backend only on the user-selected main branch; preserve the pre-existing uncommitted budget/planning slice. No paid calls, frontend, retrieval indexes or source discovery.

Reach: upload/document/version/source/job routes; existing collection authority and pagination; private artifact storage; immutable documentation selections; Alembic/models; Procrastinate ingestion queue and restricted worker login; isolated text parser; synthetic and frozen official fixtures; runtime/draft contracts and runbooks.

## Execution ledger

- Read tasks 3A, PRD, architecture, rules and current authority/migration/test patterns. TDD and executing-plans guide implementation inline; fresh review follows verification.
- Ruling: one explicitly selected TXT/Markdown page per immutable documentation selection in 3A. No crawling or HTML parsing; broader formats/source coverage remain Task 8. Version coverage is explicit, including rolling FastAPI snapshots.
- Ruling: local snapshot preparation can complete without hosted inference; document status remains awaiting_approval or waiting_capacity. No fake transport is shipped as a production provider or represented as semantic indexing. Test transports exercise the same authorization boundary.
- Ruling: private generated artifacts precede DB references; failures remove new artifacts and periodic reconciliation removes unreferenced artifacts. Queue insertion shares the metadata transaction via Procrastinate's SQL deferral function, serving as the transactional outbox.

## Checkpoints

- [ ] RED: upload/worker/publication/idempotency/access/failure tests; frozen fixtures and parser/fetch trust-boundary tests.
- [ ] GREEN: storage, parsing, migration/models, transactional queue, APIs and worker recovery.
- [ ] Verification: restricted logins, post-wait revocation/deletion, stale-worker fencing, schema comparison/downgrade, full backend suite, contracts and whitespace.
- [ ] Review, documentation/handoff and completion evidence.

No existing changes will be committed together with this slice without separating ownership. Development DB credentials/volumes remain untouched.
