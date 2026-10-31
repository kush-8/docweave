# Private ingestion and shared preparation

Private uploads/imports are owner-authorized through the project and upstream GitHub access. Current accepted formats are bounded TXT/Markdown. Validate media/body/parts before storing private bytes; run isolated parsing with bounded output and immutable content hashes/locators. `INGESTION_STORAGE_ROOT` is private and must never be served as static HTTP.

Run `python -m docweave.worker` in the configured backend source environment with `WORKER_DATABASE_URL`. Run `python -m docweave.workers.personal` separately for repository/conversation and shared catalog jobs. Both use existing Procrastinate infrastructure. API startup does not create in-process background ingestion substitutes.

Upload metadata, job intent and queue publication are transactional. Repeated delivery/content does not create duplicate immutable versions. Failed replacements retain last good snapshots; uncertain commit confirmation preserves referenced artifacts. Parser failure/timeouts have bounded retry behavior; unknown paid completion must never replay automatically.

Assess exact version/hash/parser/rules before indexing. Injection-flagged private content needs current owner review; credentials cannot be waived. Source imports require immutable operator-approved target/origin/path/coverage and current selection. Enforce public DNS/IP pinning, allowed origin/path, robots, bounded responses and no unsafe redirects/private network access. URL presence alone is not authority.

Shared catalog ingestion needs operator-approved public source/provider authority and service accounting, never private-project consent. Deduplicate active work and publish indexes atomically in the active generation. Required-source turns wait only for active identified work and resume the original intent when eligible indexes publish. Private hosted-indexing automation, catalog review/rescan/retry, complete cleanup/retention and recovery cases remain in [tasks](../tasks.md).

Tests: `backend/tests/rag/test_ingestion.py`, `test_sources.py`, `test_parser_isolation.py`, `test_shared_ingestion.py`, and `backend/tests/personal/test_personal_api.py`. They use current application fixtures and controlled IO; no retired app is required.
