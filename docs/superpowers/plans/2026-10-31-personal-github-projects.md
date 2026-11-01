# Personal GitHub project plan

Current implementation exists; fresh-start database migration is complete at `0028_sync_retries` with a verified private backup of old data. Separate accounting reconciliation, retained-schema cleanup and remaining acceptance are tracked in [tasks](../../tasks.md). The user's later explicit reset instruction supersedes preservation-based development cutover; the preservation requirements below still apply to deliberate restoration of older data. Full release is incomplete.

## Goal and authority

DocWeave is a personal technical-documentation assistant and AI engineering showcase. Each user owns their projects and conversations; there is no collaboration or workspace product. This plan supersedes older workspace, multi-provider-login, optional-GitHub/manual-project, manual-rescan and tenant-allowance requirements. Existing RAG algorithms, provider choices, security controls and evaluation criteria remain in scope. Frontend integration is now authorized as part of this flow. No deployment, paid inference, data reset or automatic private-provider enablement is authorized by this plan.

## Accepted behavior

- One GitHub login through a read-only GitHub App, supporting public and private repositories. Installation/repository selection is part of onboarding. User access tokens enforce the user/App access intersection; never use installation authority to bypass a user's access.
- Project setup requires repository, short goal, branch and optional application folder; branch/root default from the repository. Derive the name and stack; keep optional notes and constraints. Bind once during setup; defer rebinding established projects.
- Every new chat checks the selected branch HEAD. Resolve once and fetch supported Python/JavaScript/TypeScript metadata at that SHA. No clone, execution, package installation, source-code embedding or raw-config model dispatch.
- Automatically apply unambiguous stack changes. Preserve declared constraints, resolved versions and selected documentation coverage separately. Unsupported, ambiguous or partial scans remain explicit; do not overwrite good memory with incomplete extraction.
- Persist structured project memory, commit provenance and context revision. Commits without semantic stack changes do not trigger reembedding. Existing chats use the latest successful project context on their next turn, with a change notice and per-turn revision capture.
- A central catalog lets all projects reuse indexed public documentation. Match technology/ecosystem and actual version coverage, not technology presence or vector similarity alone. Auto-import trusted matching sources; unknown origins and version fallbacks require review.
- Ingestion runs in the background. Unrelated questions remain usable. A question requiring actively processing documentation waits with stage messaging and resumes automatically when its indexes are searchable.

## Data and trust boundaries

Projects gain owner_user_id. Private collections, documents, chunks, jobs and conversations authorize through that project. Retain existing collection IDs internally; new projects get one default private collection and no grant-management layer.

Add immutable public catalog revisions describing canonical technology/ecosystem, documentation target, actual version coverage, bounded approved source and source revision. A collection has exactly one parent: private project or public catalog revision. Add private project catalog selections binding dependency identity to a revision and any accepted fallback. Shared rows contain public documentation only, never project stacks, repository names, selection metadata or user prompts.

Adapt all descendant foreign keys, RLS, source approvals, publication functions, worker authorization and release checks for these two scopes. Do not invent a synthetic project/workspace for public content. Public processing uses operator-approved source/provider authority and a stable service accounting identity; personal consent cannot authorize catalog publication. Catalog mutation remains operator-only.

Readiness is derived from eligible atomic index publication in the active generation, not fetched/parsed status or a separately maintained boolean. Replacement revisions remain immutable and cannot silently change accepted version coverage. Deduplicate active public ingestion and charge identities by catalog revision, document/version, generation and operation stage. Preserve uncertain claims across restarts.

Retrieval's eligible collections are the project's private collections plus its selected, ready, currently eligible catalog collections. Keep chunking, embeddings, lexical/vector algorithms, fusion and reranking. BM25 statistics must cover only this eligible corpus. Recheck scope before release. Removing one selection never deletes shared indexes; operator revocation fences all dependent selections and waiting turns. Historical citations retain snapshots but still require current eligibility.

## Synchronization and waiting turns

Use the existing queue and advisory-lock pattern. Serialize synchronization per project, resolve HEAD after acquiring the lock, and prevent stale publication. Each initializing chat waits for its repository check; same-commit checks reuse extracted facts. Failure retains the last good memory and exposes an actionable retry state instead of asserting freshness.

Query resolution returns required dependency IDs or explicit uncertainty; validate IDs against current project context. Low retrieval confidence alone never means indexing is in progress. Missing coverage produces clarification/abstention; approval, capacity and permanent failures have distinct actionable states.

Persist waiting_for_sources on the original durable turn with required targets and job references. Completion handling and worker recovery reconcile waits and atomically claim continuation once. Recheck ownership, upstream access, context, source eligibility, processing consent and budget before continuation. Reassess dependency requirements when context changed during a wait. Cancellation/deletion prevents resumption but does not cancel shared work needed elsewhere. Preserve one-active-turn and request-idempotency behavior; never replay uncertain provider calls automatically.

Record revisions on turns and, when implemented, summaries. Invalidate/rebuild version-dependent summaries after context changes and distinguish historical version-specific statements from current facts. Old assistant answers are never documentary evidence. Show actual worker stages; use an indeterminate loader unless progress is measurable.

## Interfaces

Keep /api/v1. Make /auth/login GitHub-only without method selection; retain callback, /me and logout. Implement repository/branch choices and installation/setup status. Replace workspace project creation/listing with /projects and retain /projects/{project_id}. Allow legacy projects to link a repository once.

Implement GET /catalog and return safe catalog coverage/readiness. Project views expose repository binding, synchronization state, stack/context revision and documentation states. Use existing planned project-conversation and conversation-turn paths; add initializing conversation and waiting_for_sources turn states with safe job/progress references and retry actions. Remove workspace/member/invitation/grant/allowance APIs and their reserved placeholders. Keep collection document APIs owner-authorized for compatibility.

Frontend: real GitHub login, repository/goal setup, Projects sidebar, project-required New chat, sync/indexing status, durable turns, evidence and context-change notices. Preserve draft protection, responsive layout, themes and accessibility. No pricing or sharing UI.

## Implementation and acceptance

Core direct ownership, GitHub identity/repository access, shared catalog/retrieval, commit synchronization, durable chat/source waits and frontend integration exist. Their complete acceptance and data cutover remain tracked in [tasks](../../tasks.md); that list is the active execution order. Do not recreate removed OIDC/SaaS implementations or retain obsolete endpoint tests.

Run focused meaningful regressions, serial backend tests with warnings as errors, deterministic retrieval/isolation evaluation and frontend build/lint/browser/accessibility checks. Fake-provider tests do not establish actual account or release quality. No paid evaluation rerun without explicit authorization. Preserve all existing development data and uncertain claims; rehearse/drain/back up/verify before cutover. Keep immutable Alembic migrations.

Legacy manual projects and their private knowledge remain preserved with repository setup required before new chats. Existing ambiguous records remain inaccessible until explicitly mapped; never pick an arbitrary owner. Do not promote legacy uploads into shared public content based on filename or URL. Keep measured history in memory.md and private machine-generated evidence in operator storage; do not present older fingerprints as current release evidence.

Run focused failing-then-passing tests for each behavior, the full backend suite with warnings as errors, deterministic retrieval/isolation evaluation, frontend build/lint and browser/accessibility checks. No paid evaluation rerun without existing explicit authorization. Full answer-quality evaluation remains unfinished and is not waived by this refactor.

## Guardrails retained explicitly

Retain RAG guardrails and distinguish current enforcement from remaining acceptance. See the [guardrail plan](2026-10-31-rag-guardrails.md).

- Keep deterministic injection checks, exact-document-version quarantine and owner review; public catalog reviews require operator authority, while private-document reviews require the project owner.
- Block strong credential/token/private-key/authorization/connection-string matches before external processing. Neither catalog trust nor owner/operator review waives credential blocking.
- Bind assessments to content hash, document version, parser configuration and rule revision. Recheck before indexing, retrieval, all hosted roles and evidence release, including shared catalog results and resumed turns. Updated rules invalidate stale assessments.
- Keep application-controlled instructions separate from serialized untrusted project, repository, conversation and evidence data. Reviewed documents remain untrusted evidence.
- Validate structured claims, citation membership and exact authorized spans before history/checkpoint writes and release. Invalidate dependent summaries/citations when sources or authority change.
- Preserve existing source-fetch restrictions, processing consent, global cost controls and no-automatic-replay handling. Add regressions for shared-catalog quarantine, cross-user isolation, rule changes during waits and revoked evidence release.

## End-of-refactor discussion: semantic caching

- [ ] After refactor verification, discuss semantic caching with the user; do not implement or enable it as part of this plan.

Assess measured latency, repeated-query frequency, inference cost and expected hit rate against false-match and stale-answer risk. Compare exact-request caching, retrieval-result reuse and semantic answer caching before choosing whether any cache is worthwhile. Private queries/context/answers must never be reused across users; public documentation embeddings/indexes are already shared independently of answer caching.

Any later cache proposal must define project/owner scope, context/stack revision, selected catalog/document versions, index generation, model/prompt/guardrail revision and relevant conversation state. Permission, consent, source revocation, deletion or guardrail changes invalidate eligibility; reauthorize and validate citations on every hit. Never reuse a blocked result or stale safety assessment, and evaluate near-match questions with different versions, negations and private context. Persistence/retention, eviction and observability remain discussion items, not approved implementation decisions.

## Deliberate omissions and risks

No pricing tiers, workspace compatibility API, sharing, public catalog admin UI, push webhooks, repository code ingestion, new vector database, new queue, or established-project repository rebinding. Public catalog support changes retrieval authorization even though algorithms stay the same. Question-to-dependency identification is fallible: uncertainty must clarify instead of showing false loading states.
