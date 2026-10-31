# Responsibility separation implementation

Approved direction: technical layers in both applications; separate implemented RAG stages. Preserve HTTP/UI behavior, data, policy, transaction phases, connection affinity, parser isolation and existing CLI commands. No new dependencies or future-stage skeletons.

## Checklist

- [x] Capture available baseline and preserve pending model, compatibility-test and migration changes.
- [x] Extract backend configuration, security, identity, schemas, persistence models and error translation.
- [x] Separate domain HTTP handlers, workflows and SQL repositories; keep services only where coordination earns them.
- [x] Separate RAG stages, source/provider integration, evaluation and fingerprint format.
- [x] Extract frontend page, layouts, components, hooks, routing and synthetic data.
- [x] Update callers, parser Docker entry point, worker/CLI wiring and current documentation.
- [x] Run backend, frontend and boundary checks; complete independent review.

## Ownership

Root owns backend HTTP/domain/core/db/storage/worker and docs. RAG implementer owns RAG/provider/source/compatibility/evaluation files and their tests. Frontend implementer owns frontend. Shared import rewrites happen after extraction. No concurrent database test suites.

## Progress and rulings

- Initial working changes: backend models.py and test_compatibility_probes.py modified; migration 0012_public_pilot_budget.py untracked. Preserve their exact behavior/content.
- Frontend baseline build/lint pass. Initial sandboxed backend baseline stalled; the rerun overlapped extraction and encountered an old import. No complete pre-refactor backend baseline is claimed; final full-suite evidence is recorded below.
- Ruling: retain current main checkout per docs/rules.md and existing authorized workflow; do not stash, reset or commit the user's pending work.
- Ruling: mechanically extract existing SQL into named repository functions rather than introduce a generic query framework. Trivial HTTP operations may call those repositories directly using caller-owned transactions.
- Preserved the public-pilot purpose guard and model changes. Moved the public fixture boundary into evaluation/public_fixtures.py and updated its callers without implementing pilot dispatch.
- Backend verification: 586 passed with warnings treated as errors against the guarded disposable database (146.22 seconds). Includes migrations/model comparison, authorization, uncertain commits, queue/worker recovery, evaluator CLI, provider mocks and new layer/error/fingerprint tests. An earlier pass caught the old ingestion monkeypatch target; updated it to domain_session and reran the full suite.
- Frontend verification: build and lint pass; all 19 browser/layer/routing/accessibility tests pass on installed Chrome (22.5 seconds). No style, dependency or UI-control changes.
- Parser image rebuilt successfully from the separated standard-library module set. Stable worker/evaluation/compatibility --help entry points verified without invoking operator workflows.
- Fresh independent review found no actionable issues after tracing SQL, auth, transactions, parser isolation, model registration and frontend navigation. Temporary extraction scripts removed.
- No paid provider calls, deployment, development migration or roadmap-goal resumption performed.
