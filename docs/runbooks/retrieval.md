# Scoped retrieval and component evaluation

Task 3B provides internal indexing/retrieval services and an operator evaluation CLI. It has no new browser/API inference route, production fake provider or hosted adapter. Ordinary uploads still prepare local snapshots; actual hosted indexing/dispatch is Task 3C. Generation records default disabled. Frontend integration remains deferred.

## Planned guardrail gate

Before hosted indexing, implement the [guardrail checkpoint](../superpowers/plans/2026-10-31-rag-guardrails.md). Current RLS/source/processor checks do not enforce human-review quarantine. Gate the exact version used by index input, chunk insertion/activation, retrieval and evidence release on its current assessment/review; a document status label is insufficient. Keep an older eligible index when a replacement is held, rescan on rule changes and never waive credential blocks through owner review. Reranking and later LLM roles also follow the [structured prompt rule](../rules.md#structured-prompt-writing-rule).

## Storage and authority

Migration `0009_retrieval` adds immutable model/backend/dimension/normalization/chunker/processor generations, tenant-owned chunks and a private per-document/generation searchable-version pointer. Initial storage supports 768-dimensional unit vectors; actual model compatibility remains unverified until 3C. The official `pgvector` Python integration supplies the SQLAlchemy type/reflection; no search extension or database image change is introduced.

Runtime has SELECT-only chunk access through RLS, requiring transaction-local actor, workspace **and generation** context. Current collection read grants, enabled processors, project/collection embedding consent, active searchable version, tombstones and approved source/version state are rechecked. Missing or empty authorized scope does not broaden retrieval. General chunk DML and raw index-pointer access remain denied; the worker publishes through narrow functions.

Official selections pin the approved technology/target entry as `approved_stack`. Goal/notes edits preserve that approval; a changed/removed version entry requires a new explicit review. Existing selections without a recorded entry fail closed for indexing; the migration does not invent approval history. The operator pilot SQL captures the current entry. A previously seeded identity remains immutable: a new reviewed selection ID is required to supersede an older unbound/revoked record. Owner-facing source approval remains Task 7.

`index_document` validates the captured text hash/configuration, rechecks current rights before each bounded callback batch, validates finite unit vectors, and publishes chunk batches plus the searchable pointer in one transaction after another authority check. This transport injection is used by deterministic fixtures; no local model or fake transport ships as a production fallback. Compatible retained vectors can be reactivated without another callback.

Prepared and searchable versions are distinct. A parsed replacement marks previously indexed content stale but leaves its last good searchable pointer intact. Failed embedding/publication preserves that pointer. Only complete, authorized publication switches it; A→B→A can reactivate retained A vectors. Deletion tombstones first and erases indexed chunks/pointers atomically; the ingestion worker handles private file cleanup. Superseded nondeleted versions stay retained for future authorized citations.

## Four retrieval paths

- Native lexical: PostgreSQL `english` `tsvector`/GIN plus `websearch_to_tsquery` and `ts_rank_cd`.
- BM25: `sql-bm25-ident-v1`, `k1=1.2`, `b=0.75`, logarithmic IDF and length normalization. Retrieval units are chunks. ASCII casefolded identifier tokens preserve underscores and internal dot/colon/hyphen segments. Corpus size, document frequency and average length come only from the materialized current authorized corpus. Native ranking is not labeled BM25. The [Lucene BM25 reference](https://lucene.apache.org/core/9_9_1/core/org/apache/lucene/search/similarities/BM25Similarity.html) documents the coefficient/IDF convention; the local SQL is independently tested against hand-derived values.
- Exact vectors: materialize eligible rows before cosine-distance ranking, so the shared ANN index cannot satisfy this path. Ordinary metadata indexes may still help filtering.
- HNSW: the shared cosine index, database/RLS filtering, `strict_order` iterative scans, `ef_search=100` and `max_scan_tuples=20000`. The experiment locally disables sequential/full-sort alternatives so its recorded plan actually uses HNSW; settings are recorded, not claimed as production defaults. A bounded inner nearest-neighbour query is followed by deterministic tie sorting. The graph is shared, not physically tenant-specific.

Both channels return at most 30 candidates, exact captured spans and provenance. Query vectors must be finite 768-component unit vectors; overlong/binary queries and unsupported strategies are rejected. Before release, every captured candidate is checked against current RLS again; a changed scope fails closed. Query timeouts and HNSW scan limits never trigger scope broadening.

## Reproducible development report

The [pilot dataset](../../backend/eval/fixtures/pilot-v1.json) contains ten answerable development questions plus denial, no-evidence and version cases. Supporting quotes have exact offsets into the frozen corpus; labels remain pending human review. All pilot families are development-only. This is not the frozen 150-scenario release benchmark.

Run the complete deterministic setup/CLI smoke on the guarded test service:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests/test_evaluation_protocol.py -q
```

The test uses real HTTP ingestion, scoped indexing and a separate CLI process. It retains a public/synthetic [component report](../../backend/eval/reports/component-smoke.json) in the ignored reports directory. The report verifies actual corpus hashes, records immutable generation identity, physical shared-index bytes, measured publication time, candidate IDs/ranks/scores, SQL plans, latency, eligibility counts, ANN recall and supporting-passage recall. No paid keys are used.

For an already prepared operator fixture, invoke `python -m docweave.evaluation` with `--actor`, `--workspace`, `--project`, `--generation`, one or more `--collection`, `--vectors` and `--output`. Optional `--denied-collection` supplies an actual inaccessible collection for the denial fixture; without it that case is explicitly not run. `--dataset` defaults to the frozen pilot. The operator uses the runtime database login; IDs remain subject to current DB policy. Keep reports private: EXPLAIN can contain query/filter identifiers, and the physical shared-index metric describes the shared relation. Do not expose this operator report through a browser endpoint or static assets.

The recorded-vector JSON must contain `recording_version: recorded-vectors-v1`, the immutable `generation_id`, the exact dataset file's SHA-256 in `dataset_sha256`, explicit `provenance` (`recorded_fixture` or `recorded_provider`) and one 768-component query vector per scenario ID. Optional `build_metrics` retains measurements returned by the preparation phase; absent measurements remain null, never fabricated. Files are bounded and shape/identity checked before queries run. Reports also capture the recording file hash, so old questions or another same-dimensional model cannot silently reuse a recording.

Eight configurations are registered: native-only, BM25-only, exact-only, HNSW-only and the four lexical/vector combinations. 3B executes their component channels; fusion/reranking/final context is 3C. Native/BM25 baselines are the lexical channels of their exact combinations; exact/HNSW baselines are the corresponding vector channels. No hybrid semantic score is claimed here.

`ann_recall_at_30` compares approximate IDs with exact IDs from the same scope, using at most the available exact count as denominator. An empty eligible corpus has a null value/zero denominator. `vector_fewer_than_requested` differs from `vector_underfilled_vs_eligible`: two results from two eligible chunks is not an ANN failure. Supporting recall uses labeled source identity plus exact spans, independently of ANN recall. Version/no-evidence cases record candidates and mismatches; they do not fabricate an abstention or answer before the RAG layer exists.

Every component report sets `semantic_quality_evidence=false`. Recorded fixture vectors prove policy/query/report behavior; they cannot establish a semantic winner, citation quality, answer correctness or release readiness. A corpus/hash mismatch is visible. Live adapters/account/prices, tokenizer/input limits, RRF/reranking and the retrieval quality pilot remain 3C; full answer/memory evaluation is Task 4 and held-out gates are Task 10.
