# Remaining work

The personal GitHub API, core durable worker/RAG path, shared public catalog scope and API-backed frontend exist. The product is not release-complete. This is the current execution order; individual behaviors already covered by tests need not be reimplemented.

## Required acceptance and integration

- [ ] Apply verified numeric GitHub identity mappings while preserving user UUIDs; resolve ambiguous/nonproject ownership explicitly. Back up, restore/rehearse, compare IDs/hashes/vectors/references/ledger/unknown claims, drain/migrate/resume development. Only then remove unnecessary retained database structures.
- [ ] Verify actual GitHub App callback/installations, public/private and organization/SSO access, denial, refresh/revocation and installation/setup status. Configure immutable RAG profiles/generation with verified account/capability/pricing and explicit private-processing consent. Live paid checks need separate authorization.
- [ ] Finish actionable sync retries, supported pnpm/ancestor monorepo locks and remaining force-push/concurrency/partial-scan cases. Never assert unsupported scans are complete.
- [ ] Finish unknown-source review, explicit version-fallback acceptance, real catalog coverage and distinct missing/approval/capacity/permanent-failure states. Public mutation/review stays operator-only; no public catalog admin UI is required.
- [ ] Complete worker crash/lease/restart reconciliation, duplicate-delivery continuation, cancellation/deletion and context/dependency-change recovery acceptance, rechecking current access/consent/budget before continuation. Preserve paid resolution reuse and unknown completion.
- [ ] Complete guardrail rule-update/rescan, review/audit/recovery and dependent citation/memory invalidation across private/shared sources, all hosted roles and waits. Finish private hosted-indexing integration without relaxing admission/consent.
- [ ] Implement durable context-revision-aware summaries beyond bounded recent history; rebuild invalid summaries and keep old answers out of evidence.
- [ ] Verify cleanup/retention, backup recovery, failure/recovery behavior, privacy and full answer/citation/abstention/latency/cost evaluation against [PRD criteria](PRD.md#completion-criteria); implement truthful readiness when gates are met. Readiness remains 503.
- [ ] After refactor verification, discuss whether semantic caching is useful; measure recurrence, latency, cost and false-match risk first. No cache implementation decision yet.

## Scope and evidence

Hybrid lexical/vector search, RRF/reranking, providers, guardrails and global spending protection remain. Pricing/workspaces/sharing, push webhooks, repository-code ingestion, established-project rebinding and new infrastructure remain omitted. Public indexes are already shared independently of answer caching.

See the [current change/status report](reports/2026-11-01-personal-projects-checkpoint.md), [personal plan](superpowers/plans/2026-10-31-personal-github-projects.md) and [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md). These are grouped tasks with acceptance details, not a claim that every unlisted edge case is verified. Historical measurements/decisions are only in [memory](memory.md).
