# Guardrail lifecycle implementation plan

**Goal:** Complete the existing [guardrail acceptance design](2026-10-31-rag-guardrails.md) with local LangChain scans, durable rescans, review/recovery and dependent context invalidation.

**Architecture:** Keep the existing deterministic detectors and authority predicates. A content-addressed scanner revision and monotonically increasing database policy epoch fence stale workers and approvals. Rescan exact retained artifacts using the existing personal queue; preserve snapshots, vectors and accounting. LangChain tracing is disabled around sensitive scans.

**Scope:** Core scanner, additive migration and model metadata, guardrail repository/service/operator CLI, personal worker maintenance, owner review schema, hosted admission/output validation and history rechecks. No paid calls, development migration, new summary feature or deployment.

## Execution and checks

- [x] Add failing scanner/lifecycle tests for policy activation, stale leases/review, immutable artifact corruption, private/shared review authority and citation/history invalidation.
- [x] Implement local LangChain normalization/detection with content-addressed revisions; retain the `assess_text` interface and safe findings.
- [x] Add policy/epoch, durable rescan jobs and content-free audit events. Replace hard-coded SQL revisions with current policy, verify parser bindings and current reviewer authority; activate policy atomically and hold stale assessments immediately.
- [x] Reconcile/recover bounded jobs on the existing queue, publish under current epoch/token/hash checks, retain compatible vectors, resume approved work/waits, and provide bounded operator audit/review/retry commands.
- [x] Fence hosted dispatch/recovery against policy changes; validate generated text before checkpointing, and recheck cached conversation history before each hosted stage.
- [x] Run focused then serial backend checks, migration/model checks and whitespace checks. Final serial backend verification: 664 passed in 254.57 seconds with warnings as errors; evidence is `logs/guardrail-final-20261103.xml`. Lock, compile, scanner/migration revision and documentation-link checks pass. Independent review findings were fixed and rechecked. Development rollout, paid-provider acceptance and full release evaluation remain separate.

## Review focus

- A→B→A rule activation cannot revive an old approval or stale lease.
- Review cannot waive credentials, parser mismatch, ownership loss or deleted content.
- Restored stale assessments and missing/corrupt artifacts stay held; retry never replays a provider call.
- Current and retained older indexed versions are rescanned without new embeddings.
- History cached before revocation cannot enter another hosted stage; incurred/uncertain charges remain.
