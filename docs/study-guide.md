# Studying DocWeave

Start with [product requirements](PRD.md), [architecture](architecture.md) and [current implementation inventory](study-inventory.md). Then trace these paths through code and tests:

1. GitHub login: settings, read-only transport, state/PKCE, encrypted sessions/refresh and current upstream identity.
2. Project setup: direct ownership, repository binding, commit-pinned metadata scanning, semantic context revisions and honest incomplete states.
3. Knowledge: immutable public revisions/private selections, private upload snapshots, assessments/review and operator publication authority.
4. Retrieval: selected corpus scope, native/BM25, exact/HNSW, RRF, reranking and current generation/version eligibility.
5. Durable turns: idempotent request admission, query resolution, source waits, continuation/recovery and cancellation.
6. Provider boundary: structured untrusted envelopes, explicit consent, immutable profiles, conservative spending/dispatch and uncertainty.
7. Answer/evidence: claim/reference validation before writes, exact spans and read-time revocation.
8. Frontend: API state, routing/draft protection, accessible responsive views and sign-out race protection.
9. Verification: guarded serial DB tests, deterministic HTTP/browser fixtures and reproducible component evaluation versus remaining live/release evidence.

For each path, explain its trust boundary, read the happy path and one failure/revocation test, then identify what the test does not prove. Use [tasks](tasks.md) to distinguish implemented mechanics from remaining acceptance. Historical lessons/decisions are in [memory](memory.md); current docs do not retain obsolete architecture snapshots.
