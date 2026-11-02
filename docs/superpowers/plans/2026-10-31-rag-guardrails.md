# RAG guardrail acceptance plan

The lifecycle implementation uses local LangChain Core checks, version/hash/parser/rule/epoch-bound assessments, durable rescans, private owner/public operator review, safe audit records and citation/summary invalidation. Existing database functions and the queue retain authority; no hosted detector is selected. See the [implementation plan](2026-11-02-guardrail-lifecycle.md) and [operator runbook](../../runbooks/guardrails.md). Full release evaluation and development cutover remain separate acceptance gates.

## Required invariants

- Scan document/query/generated query/summary content with bounded rules for instruction override, role spoofing and secret exposure. Keep legitimate security examples reviewable. Strong keys/tokens/auth headers/credential-bearing URIs are blocked; explicit placeholders are distinguished. No automatic redaction or review waiver for credentials.
- Bind eligibility to immutable version, content hash, parser configuration and current rule revision. Store safe finding/rule IDs without matched credentials; normalization is scan-only and never changes snapshot/locators. Missing/failed/held assessments fail closed.
- Private review requires current owner; public catalog review requires operator authority. Bounded review pages and CSRF/revision checks cannot be bypassed by ownership loss, deletion or rule/hash changes. Approval grants no source, provider, consent or spending authority.
- Recheck at index input/insertion/publication, all hosted-role dispatch, chunk retrieval, wait continuation and evidence/history release. Updated rules hold affected versions pending rescan; clean versions resume, flagged versions require current review. Protect the actual indexed version and eligible older snapshots; A→B→A reuse must not reembed compatible retained vectors.
- Shared builders separate trusted task/rules/output from JSON-serialized query/project/conversation/evidence. Role tags and instructions in untrusted data cannot authorize actions. Provider preflight uses segment provenance so reviewed evidence can be used as data without waiving credentials.
- Structured output separates documentary claims, project facts and visibly inferred advice. Validate schema, supplied-reference membership, exact spans/locators/version/current authority before history/checkpoint writes; construct citation URLs/IDs server-side. Invalid citations abstain, malformed output fails, access/credential violations block. Preserve all incurred/uncertain charges and do not automatically regenerate rejected answers.

## Lifecycle verification

Focused verification covers rule activation including A→B→A and same-rule restore fencing, old lease rejection, missing-artifact retry, retained vector reuse, exact owner/operator review, cross-user denial, credential blocks, parser-bound review pages, audit pagination, current source/wait states, hosted policy changes and rejection before checkpointing. Migration roundtrip, metadata parity, recovery preservation, admitted private indexing/RAG and durable summary integration pass. Final serial backend verification on 2026-11-03: **664 passed in 254.57 seconds**, with warnings as errors. Independent review findings were fixed and rechecked. Development cutover and full release evaluation remain separate.

## Remaining release acceptance

- [x] Implement shared/private exact-version review, safe older-index retention and idempotent processing after review.
- [x] Implement rule-update queue rescans, stale-assessment holds, dependent summary/citation invalidation and restore fencing.
- [x] Guard implemented hosted roles, decoded generated text and recovery checkpoints; synthetic/public runners use the same checks. Offline judges remain unimplemented and cannot bypass these checks when introduced.
- [x] Exercise cross-user/operator boundaries, stale epochs/leases and hosted/history release checks with disposable data and mocked HTTP.
- [ ] Complete the separately tracked cleanup/retention and live backup/development-cutover acceptance; lifecycle audit/recovery and private hosted-indexing integration are implemented.
- [ ] Report detection/false-positive/overhead outcomes alongside the full answer/citation/abstention/privacy evaluation. Preserve 150 scenarios, 100/50 development/held-out and separate 30-output human reviews. No guard/judge bypass for evaluation.

Current tests use controlled disposable data and mocked provider HTTP. They do not guarantee complete detection or semantic faithfulness. See [rules](../../rules.md), [tasks](../../tasks.md) and [current report](../../reports/2026-11-01-personal-projects-checkpoint.md).
