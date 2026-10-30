# Task 3B — scoped indexes and evaluation foundation

Execute inline with TDD and Ponytail/code-simplification. Continue on user-selected `main`, preserving the pre-existing budget slice and the verified uncommitted Task 3A slice. Current verified baseline: 476 backend tests, warnings as errors. No paid calls, frontend, production default selection or deployment.

## Confirmed decisions and scope

- The user explicitly chose **SQL BM25**, with corpus statistics limited to the current authorized corpus; do not add a search extension or change the PostgreSQL image.
- Implement native PostgreSQL full-text and SQL BM25, filtered exact vector ranking and shared HNSW with RLS/database metadata filtering plus bounded iterative scans. No result broadening on empty or underfilled scope.
- Use prepared/recorded vectors and fake transports only in deterministic tests/evaluation. There is no production fake provider or automatic local fallback. Task 3C owns actual embedding/reranking adapters, consent/profile migration, tokenizers, paid dispatch/reservations and live quality evidence.
- Initial candidate dimensionality remains 768; generation records pin model/backend/dimensions/normalization/parser identity. Incompatible generations must never mix.
- Official source eligibility must retain the immutable selection's project/context/version scope; private uploads stay collection/project-owned. Current grants, active versions, tombstones, active selections and processor approval apply before text leaves the database/worker boundary and at index publication.

## Reach

`models.py`, migration `0009_retrieval`, guarded disposable fixture cleanup, `retrieval.py`/index service, `evaluation.py`, versioned development fixtures/configs under `backend/eval`, tests `test_retrieval.py`/`test_evaluation_protocol.py`, seed metadata where needed, API/status/runbooks/tasks/memory. Reuse Actor, tenant_session, private ArtifactStore, immutable document snapshots, existing processor policy and financial functions. Do not alter unrelated auth/budget behavior.

## Work and evidence ledger

- [x] RED/GREEN: scoped publication; wrong-tenant/unapproved fake inputs; generation, source/version, revocation, tombstone and final release checks.
- [x] Immutable generations, chunk/vector storage, explicit generation RLS and narrow atomic publication/pointer functions; general runtime DML denied.
- [x] Native identifiers and SQL BM25 values/statistics isolation; fixed k1/b and tokenization identity.
- [x] Exact/HNSW real plans, shared database filters, underfill/ANN denominators and bounded settings.
- [x] Evaluator CLI/schema, ten development answerable cases plus boundaries, eight registered component configurations. Fusion/reranking/semantic quality remain 3C.
- [x] Actual plans/ranks/timing, index size/publication time, recording/corpus identity and separate ANN/support metrics retained in the controlled smoke artifact.
- [x] Full suite/model/downgrade/contract checks, fresh review and fixes, docs/handoff. Full suite: **505 passed**; metadata-only follow-up: **13 evaluator tests passed**. Lock/Compose/whitespace passed. No deferred minor findings.

2026-10-31 evidence: initial seven retrieval setup failures and seven evaluator failures established RED. Targeted regressions then caught the HNSW optimizer choosing a metadata index, stale source approval after goal edits, evidence release after revocation, chunk retention after tombstone, missing generation RLS, incorrect supporting-span metrics and unbound corpus identity. Fresh review found last-good searchable replacement loss, unbound recorded query vectors and oversized integer conversion; each received an observed failing regression and a fix. Searchable activation is now per-document/generation and atomic with all chunk inserts, retaining the previous searchable version through failed embedding.

Full backend verification after the review fixes: **505 passed** with warnings as errors, including model comparison and migration downgrade/re-upgrade. The real frozen-corpus evaluator CLI produced a matching-corpus component report with 13 cases/8 registered configurations, actual SQL plans, generation/dataset/recording identities, physical index size and measured publication times. No semantic quality or paid inference is claimed. A final metadata-only addition records lexical configuration and retrieval source hash; all **13 evaluator tests passed** afterward.

User confirmed they will configure Gemini/Groq keys and restore development DB access for 3C. Preserve their configuration; do not use or print secrets. Real calls still require verified profiles/prices, explicit processor consent and the durable reservation/dispatch gates under the US$0.25 probe ceiling.

## Primary references already checked

- PostgreSQL 17 text search: https://www.postgresql.org/docs/17/textsearch-controls.html
- pgvector filtering/iterative scans/exact versus approximate search: https://github.com/pgvector/pgvector
- Lucene BM25 coefficients/IDF reference: https://lucene.apache.org/core/9_9_1/core/org/apache/lucene/search/similarities/BM25Similarity.html

These references guide implementation; they do not establish local plans, measured quality or account/provider capability.
