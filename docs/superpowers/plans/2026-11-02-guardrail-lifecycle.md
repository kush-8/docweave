# Guardrail lifecycle implementation plan

**Goal:** Complete the existing [guardrail acceptance design](2026-10-31-rag-guardrails.md) with local LangChain scans, durable rescans, review/recovery and dependent context invalidation.

**Architecture:** Keep the existing deterministic detectors and authority predicates. A content-addressed scanner revision and monotonically increasing database policy epoch fence stale workers and approvals. Rescan exact retained artifacts using the existing personal queue; preserve snapshots, vectors and accounting. LangChain tracing is disabled around sensitive scans.

**Scope:** Core scanner, additive migration and model metadata, guardrail repository/service/operator CLI, personal worker maintenance, owner review schema, hosted admission/output validation and history rechecks. No paid calls, development migration, new summary feature or deployment.

## Execution and checks

- [ ] Add failing scanner/lifecycle tests for policy activation, stale leases/review, immutable artifact corruption, private/shared review authority and citation/history invalidation.
- [ ] Implement local LangChain normalization/detection with content-addressed revisions; retain the `assess_text` interface and safe findings.
- [ ] Add policy/epoch, durable rescan jobs and content-free audit events. Replace hard-coded SQL revisions with current policy, verify parser bindings and current reviewer authority; activate policy atomically and hold stale assessments immediately.
- [ ] Reconcile/recover bounded jobs on the existing queue, publish under current epoch/token/hash checks, retain compatible vectors, resume approved work/waits, and provide bounded operator audit/review/retry commands.
- [ ] Fence hosted dispatch/recovery against policy changes; validate generated text before checkpointing, and recheck cached conversation history before each hosted stage.
- [ ] Run focused then serial backend checks, migration/model checks and whitespace checks. Update operational docs with actual results and remaining acceptance limits.

## Review focus

- A→B→A rule activation cannot revive an old approval or stale lease.
- Review cannot waive credentials, parser mismatch, ownership loss or deleted content.
- Restored stale assessments and missing/corrupt artifacts stay held; retry never replays a provider call.
- Current and retained older indexed versions are rescanned without new embeddings.
- History cached before revocation cannot enter another hosted stage; incurred/uncertain charges remain.
