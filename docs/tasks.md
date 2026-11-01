# Remaining work

The personal GitHub API, core durable worker/RAG path, shared public catalog scope and API-backed frontend exist. The product is not release-complete. This is the current execution order; individual behaviors already covered by tests need not be reimplemented.

## Completed migration

- [x] Complete the authorized fresh-start development migration to `0028_sync_retries`. Schema check passes; old application records and queued jobs are empty, only the built-in service identity remains, and all three restricted logins work. The private pre-reset backup was restored and all 32 original application/queue tables matched; its hashes remain verified. Old-user mapping is unnecessary for the fresh start. Linking/preservation tools remain available for deliberate restoration of older data; see the [operator steps](runbooks/personal-projects.md#preserved-data-migration).

## Required acceptance and integration

- [ ] **In progress:** Verify actual GitHub App callback/installations, public/private and organization/SSO access, denial, refresh/revocation and installation/setup status. Configure immutable RAG profiles/generation with verified account/capability/pricing and explicit private-processing consent. Reconcile archived incurred/unknown charges before enabling paid processing; reset does not authorize replay. Live paid checks need separate authorization.
- [ ] **In progress:** Finish actionable asynchronous sync retries, supported pnpm/ancestor monorepo locks and remaining force-push/concurrency/partial-scan cases. Never assert unsupported scans are complete.
  - Same-chat HTTP 202 retries, safe failure progress, pnpm 9.0 importers and npm ancestor lock scoping are implemented. Focused backend checks: 73 passed; sync browser checkpoint: 14 passed, with build/lint passing. Force-push, concurrent-worker, partial-memory and additive 0029 stale-publication checks pass. Combined-worktree contract integration, remaining format coverage and live operational acceptance keep this task open. See the [sync plan](superpowers/plans/2026-11-01-repository-sync.md).
- [ ] **In progress:** Finish unknown-source review, explicit version-fallback acceptance, real catalog coverage and distinct missing/approval/capacity/permanent-failure states. Public mutation/review stays operator-only; no public catalog admin UI is required.
  - Owner coverage/selection UI and API, target-bound fallback acceptance, persistent deselection, operator manifest review/revocation, package aliases and distinct source states are implemented. Retrieval and retained evidence share current selection checks. Three real publisher pages are pinned by release commit and content hash. Publisher-linked discovery, private unknown-source review and verified bounded coverage of all 29 required entries remain open; examples and mocked tests do not complete catalog acceptance. See the [catalog runbook](runbooks/catalog.md).
- [ ] **In progress:** Complete worker crash/lease/restart reconciliation, duplicate-delivery continuation, cancellation/deletion and context/dependency-change recovery acceptance, rechecking current access/consent/budget before continuation. Preserve paid resolution reuse and unknown completion.
- [ ] Complete guardrail rule-update/rescan, review/audit/recovery and dependent citation/memory invalidation across private/shared sources, all hosted roles and waits. Finish private hosted-indexing integration without relaxing admission/consent.
- [ ] Implement durable context-revision-aware summaries beyond bounded recent history; rebuild invalid summaries and keep old answers out of evidence.
- [ ] Review retained database structures and remove only those no longer referenced; keep active financial/operator/restoration dependencies. Verify cleanup/retention, backup recovery, failure/recovery behavior, privacy and full answer/citation/abstention/latency/cost evaluation against [PRD criteria](PRD.md#completion-criteria); implement truthful readiness when gates are met. Readiness remains 503.
- [ ] After refactor verification, discuss whether semantic caching is useful; measure recurrence, latency, cost and false-match risk first. No cache implementation decision yet.

## Scope and evidence

Hybrid lexical/vector search, RRF/reranking, providers, guardrails and global spending protection remain. Pricing/workspaces/sharing, push webhooks, repository-code ingestion, established-project rebinding and new infrastructure remain omitted. Public indexes are already shared independently of answer caching.

See the [current change/status report](reports/2026-11-01-personal-projects-checkpoint.md), [personal plan](superpowers/plans/2026-10-31-personal-github-projects.md) and [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md). These are grouped tasks with acceptance details, not a claim that every unlisted edge case is verified. Historical measurements/decisions are only in [memory](memory.md).
