# Personal GitHub Projects Implementation Plan

Status: user-approved direction, 2026-10-31. Documentation must be updated before code. Implementation has reached the 2026-11-01 checkpoint; preserved-data cutover and release work remain. See the [checkpoint report](../../reports/2026-11-01-personal-projects-checkpoint.md) for implemented behavior, evidence and remaining tasks.

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

Record revisions on turns and summaries. Invalidate/rebuild version-dependent summaries after context changes and distinguish historical version-specific statements from current facts. Old assistant answers are never documentary evidence. Show actual worker stages; use an indeterminate loader unless progress is measurable.

## Interfaces

Keep /api/v1. Make /auth/login GitHub-only without method selection; retain callback, /me and logout. Implement repository/branch choices and installation/setup status. Replace workspace project creation/listing with /projects and retain /projects/{project_id}. Allow legacy projects to link a repository once.

Implement GET /catalog and return safe catalog coverage/readiness. Project views expose repository binding, synchronization state, stack/context revision and documentation states. Use existing planned project-conversation and conversation-turn paths; add initializing conversation and waiting_for_sources turn states with safe job/progress references and retry actions. Remove workspace/member/invitation/grant/allowance APIs and their reserved placeholders. Keep collection document APIs owner-authorized for compatibility.

Frontend: real GitHub login, repository/goal setup, Projects sidebar, project-required New chat, sync/indexing status, durable turns, evidence and context-change notices. Preserve draft protection, responsive layout, themes and accessibility. No pricing or sharing UI.

## Ordered implementation and acceptance

- [x] Record approved design and execution order in authoritative docs before code changes.
- [ ] Ownership foundation: add migration preflight and regression tests; map sole-owner workspaces automatically, require explicit mappings for ambiguous ownership and nonproject records. Preserve ledger actor IDs and operation identities rather than merging hashes. Prove cross-user denial through SQL and APIs.
- [ ] GitHub identity: replace OIDC transport and Keycloak infrastructure using existing session/security primitives. Preserve user UUIDs through explicit verified numeric-GitHub-ID mappings; never email-match. Test callback replay, denied installation, token refresh races and upstream revocation.
- [ ] Catalog: add public revisions, collections and private selections; adapt source policy, ingestion, publication and retrieval. Test shared-job deduplication, exact generation/version readiness, operator-only mutation, revocation, and private isolation across users.
- [ ] Repository synchronization: supported static parsers, commit-pinned provenance and semantic diff; test no-op commits, monorepos, partial/unsupported input, force pushes and concurrent new chats.
- [ ] Conversations and waiting turns: wire existing RAG components; test unrelated questions during indexing, required-source waits, restart reconciliation, exactly-once resume, cancellation, failure and context changes.
- [ ] Frontend integration and cleanup: replace synthetic-only navigation with the agreed flow, remove obsolete routes/config/callers/fixtures, and update runtime contracts/runbooks as each slice lands.
- [ ] Cutover verification: rehearse a disposable restored database first; drain workers, back up development database/artifacts, migrate without resetting storage, verify counts/references/hashes/vectors/ledger claims, then resume workers. Remove obsolete runtime tables/functions only after reference and preservation checks pass. Keep historical migrations.

Legacy manual projects and their private knowledge remain preserved with repository setup required before new chats. Existing ambiguous records remain inaccessible until explicitly mapped; never pick an arbitrary owner. Do not promote legacy uploads into shared public content based on filename or URL. Historical reports remain intact and explicitly historical after source fingerprints change.

Run focused failing-then-passing tests for each behavior, the full backend suite with warnings as errors, deterministic retrieval/isolation evaluation, frontend build/lint and browser/accessibility checks. No paid evaluation rerun without existing explicit authorization. The original full answer-quality evaluation remains unfinished and is not waived by this refactor.

## Guardrails retained explicitly

User reconfirmed on 2026-10-31: keep the previously approved RAG guardrails. Preserve the distinction between existing enforcement and planned protection; this refactor does not make pending guards implemented by declaration.

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
