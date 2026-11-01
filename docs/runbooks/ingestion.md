# Private ingestion and shared preparation

Private uploads/imports are owner-authorized through the project and upstream GitHub access. Uploads accept bounded TXT/Markdown; reviewed public-source imports additionally support static HTML through the isolated parser. Validate media/body/parts before storing private bytes; retain actual fetched MIME and immutable content hashes/locators. `INGESTION_STORAGE_ROOT` is private and must never be served as static HTTP.

Run `python -m docweave.worker` in the configured backend source environment with `WORKER_DATABASE_URL`. Run `python -m docweave.workers.personal` separately for repository/conversation, shared catalog and private index jobs. Its periodic reconciliation discovers eligible parsed artifacts, deduplicates index intents and recovers stalled deliveries. Both use existing Procrastinate infrastructure. API startup does not create in-process background ingestion substitutes.

Upload metadata, job intent and queue publication are transactional. Repeated delivery/content does not create duplicate immutable versions. Failed replacements retain last good snapshots; uncertain commit confirmation preserves referenced artifacts. Parser failure/timeouts have bounded retry behavior; unknown paid completion must never replay automatically.

Assess exact version/hash/parser/rules before indexing. Injection-flagged private content needs current owner review; credentials cannot be waived. Shared sources need operator approval; private publisher sources need explicit version-bound owner approval. Enforce immutable target/origin/path/coverage, current selection, public DNS/IP pinning, robots, bounded responses and no unsafe redirects/private network access. URL presence alone is not authority. See the [catalog workflow](catalog.md).

Shared catalog ingestion needs operator-approved public source/provider authority and service accounting, never private-project consent. Deduplicate active work and publish indexes atomically in the active generation. Required-source turns wait only for active identified work and resume the original intent when eligible indexes publish. Private hosted-indexing automation, catalog review/rescan/retry, complete cleanup/retention and recovery cases remain in [tasks](../tasks.md).

Tests: `backend/tests/rag/test_ingestion.py`, `test_sources.py`, `test_parser_isolation.py`, `test_shared_ingestion.py`, and `backend/tests/personal/test_personal_api.py`. They use current application fixtures and controlled IO; no retired app is required.
