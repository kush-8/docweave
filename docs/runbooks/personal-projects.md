# Personal GitHub projects

This is the active setup guide. See [tasks](../tasks.md) for remaining acceptance and [memory](../memory.md) for history.

## Setup

Use a GitHub App with Contents read-only and Metadata read-only. The web authorization flow establishes identity; installation selects repositories. Configure `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `AUTH_ENCRYPTION_KEY`, `APP_ORIGIN` and the explicit loopback-only HTTP development exception. Never put credentials in URLs, logs or browser storage.

With local Vite, use its browser origin (normally `http://127.0.0.1:5173`) and callback `/api/v1/auth/callback`; Vite forwards `/api` to backend port 58000. Organization installation/SSO approval can still be required. GitHub's selected-repository Contents permission is broader than the application's metadata-file allowlist.

Set `RAG_GENERATION_ID`, `EMBEDDING_PROFILE_ID`, `QUERY_PROFILE_ID`, `RERANK_PROFILE_ID` and optionally `ANSWER_PROFILE_ID` only to operator-verified immutable records. Configure provider keys privately. Source approval, account/capability/pricing checks, user processing consent and the shared US$20 monthly cap still apply. No workspace quotas or commercial tiers remain in the product.

Run the ingestion worker and the personal worker separately. Both use `WORKER_DATABASE_URL`; personal retrieval uses the restricted `DATABASE_URL`. Public catalog ingestion reuses existing source-fetch, parser, chunking and embedding contracts. Its current source format support remains bounded TXT/Markdown.

## Preserved-data migration

No development migration or reset was performed in this checkpoint. Do not discard existing storage, backups, identity records or charge claims to obtain a clean start.

1. Run the read-only ownership preflight (`python -m docweave.ownership`) with the backend source environment. It reports ambiguous project ownership and accepts explicit project-to-existing-user UUID mappings.
2. Resolve identity linking explicitly by verified numeric GitHub identity; never auto-link by email. The operator application of these identity mappings and full restored-data rehearsal remain outstanding tasks.
3. Back up database/artifacts, rehearse the additive migrations on an isolated restored copy and verify IDs, hashes, vector counts, source references and all cost/uncertainty claims.
4. Drain workers, perform the verified cutover, check current authorization and resume workers. Keep legacy schema/functions until preservation-backed removal is safe.

Sole workspace owners backfill directly. Ambiguous legacy projects remain unassigned; legacy manual projects require a repository before starting new chats. Additive migrations currently reach `0027_personal_source_scope`; application startup never runs them automatically.

## Operational limits and recovery

- Partial/unsupported stack scans retain good memory and block the initializing chat rather than asserting freshness. pnpm and some ancestor monorepo lock mappings remain explicit unsupported cases.
- A turn waits only for identified required dependencies with active ingestion work. Completion wakes its original durable intent; query-resolution results are retained across a source wait. Failed, approval-blocked and capacity states must not be shown as indexing progress.
- Unknown completion is never replayed automatically. Provider claims retain conservative charges even if a response or publication acknowledgement is lost.
- Guardrail review binds the exact document version/hash/rules. Credentials cannot be waived. Shared catalog review requires operator authority; ordinary project APIs cannot publish or mutate shared catalog content.
- Retained citations are rechecked at read/release; revocation can hide an old answer. Hybrid search does not bypass source, version, private-owner, processor or guardrail policy.

Live GitHub/provider compatibility, development migration, full release evaluation and remaining recovery/guardrail operations are intentionally not claimed by mocked/disposable verification. See the [checkpoint and remaining tasks](../reports/2026-11-01-personal-projects-checkpoint.md).
