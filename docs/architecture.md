# Architecture

## Runtime

One modular FastAPI application, PostgreSQL/pgvector, Procrastinate workers and a React/TypeScript/Vite frontend. GitHub is the only identity and repository-access provider. Groq serves hosted LLM roles; Gemini serves embeddings. No new queue, vector database or guardrails framework is needed.

`docweave.main:create_app` composes `api/application.py`. Routes call services and repositories; SQL stays in persistence/database layers. `core` owns shared contracts, settings, identity and deterministic guardrails. `integrations` owns bounded external IO, `rag` the retrieval stages, `storage` private artifacts and `evaluation` reproducible reports. Lower layers do not import HTTP/application composition. Current document routes depend directly on personal resource authorization; there is no copied SaaS application or dependency-override compatibility layer.

## Ownership and data

Users own projects and private conversations/collections. Projects bind a GitHub repository/branch/folder and structured memory with commit provenance/context revision. Private documents, versions, jobs, chunks and evidence authorize through that project. Public catalog revisions own shared collections; each collection has exactly one private-project or public-revision parent. Private project selections bind dependency identity and accepted coverage to an immutable revision. Public rows must never contain project stacks, repository names, selections, prompts or private uploads.

Catalog publication and review require operator/service authority. Public indexing is deduplicated by revision/document/version/generation/stage and uses a stable accounting identity. A selection does not confer publication authority. Readiness comes from eligible atomic index publication in the active generation, not fetched/parsed flags. Revocation fences dependent turns/citations without deleting shared indexes selected elsewhere.

Retained workspace tables/functions support financial operations and deliberate restoration of older backups. They are not a product API. Development is freshly initialized at `0027_personal_source_scope`; startup does not migrate. The private pre-reset backup has passed isolated restoration and row comparisons. Archived incurred/unknown charges need reconciliation before paid processing. Restoring older users requires explicit ambiguous ownership/verified numeric GitHub identity mapping and preservation checks; no email auto-link.

## Requests and jobs

GitHub OAuth uses state/PKCE and encrypted cookies/tokens. Refresh is serialized and numeric identity is rechecked; repository visibility is checked before private release. Transaction-local actor settings and restricted database roles enforce scope. Browser mutations require exact Origin and CSRF; private responses are not browser-persisted.

Serialize repository synchronization per project; resolve HEAD after lock acquisition and fetch metadata pinned to that SHA. Semantic changes revise memory; incomplete scans preserve last good memory. Durable conversations and one-active-turn/idempotency constraints precede jobs. Query resolution validates required dependency IDs; uncertainty clarifies or abstains. Source waits retain resolution and original intent; completion/recovery claims continuation once and rechecks all authority/context/policy/budget. Cancellation/deletion must fence resumption without cancelling shared work needed elsewhere.

## Retrieval and generation

Eligible scope is current private collections plus selected, ready, permitted public collections. Native full text/BM25 and exact/HNSW vector channels remain available; BM25 statistics use only eligible selected corpus. RRF fuses channels and Groq reranks before structured generation. Worker defaults are provisionally BM25/exact, not a benchmark winner. Generated claims refer only to supplied context/evidence; server validates exact spans, membership/version and current authority before persistence/release. Old answers never become documentary evidence.

Recent history is bounded to 6000 tokens; durable revision-aware summaries remain unfinished. Citation/history reads reauthorize retained evidence. Structured prompts keep trusted rules separate from JSON-serialized untrusted data for every role. Deterministic assessments bind version/hash/parser/rule and block credentials regardless of review. See the [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md).

## Spending and recovery

Immutable profile IDs bind model/backend/processor/prices/token bounds. Verified account/capability/pricing, consent and source eligibility precede dispatch. Global admission is serialized under the shared US$20 monthly cap using Asia/Calcutta months. Journal body hashes and conservative claims before HTTP; no transport retries or automatic replay of unknown completion. Retain incurred/uncertain charges if output is rejected. Operator synthetic/public runners have separate bounded fixed-input authority, never private-processing authority.

Private uploads use bounded TXT/Markdown validation, isolated parsing and atomic immutable snapshot/index publication. Replacement failures preserve good snapshots. Deletion tombstones/fences first; complete cleanup/backup recovery and rule-rescan workflows require remaining acceptance work. Liveness is implemented; readiness remains 503. See [tasks](tasks.md) for gaps and [database operations](runbooks/database.md) for migration safety.
