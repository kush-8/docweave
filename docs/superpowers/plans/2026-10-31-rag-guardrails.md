# RAG guardrail acceptance plan

Deterministic version-bound assessments, credential blocks, owner review, shared structured prompts and validated citations are implemented in the current core. This does not complete the full operational protection matrix. Use existing scanners, database functions and queue; no hosted detector or new framework is selected.

## Required invariants

- Scan document/query/generated query/summary content with bounded rules for instruction override, role spoofing and secret exposure. Keep legitimate security examples reviewable. Strong keys/tokens/auth headers/credential-bearing URIs are blocked; explicit placeholders are distinguished. No automatic redaction or review waiver for credentials.
- Bind eligibility to immutable version, content hash, parser configuration and current rule revision. Store safe finding/rule IDs without matched credentials; normalization is scan-only and never changes snapshot/locators. Missing/failed/held assessments fail closed.
- Private review requires current owner; public catalog review requires operator authority. Bounded review pages and CSRF/revision checks cannot be bypassed by ownership loss, deletion or rule/hash changes. Approval grants no source, provider, consent or spending authority.
- Recheck at index input/insertion/publication, all hosted-role dispatch, chunk retrieval, wait continuation and evidence/history release. Updated rules hold affected versions pending rescan; clean versions resume, flagged versions require current review. Protect the actual indexed version and eligible older snapshots; A→B→A reuse must not reembed compatible retained vectors.
- Shared builders separate trusted task/rules/output from JSON-serialized query/project/conversation/evidence. Role tags and instructions in untrusted data cannot authorize actions. Provider preflight uses segment provenance so reviewed evidence can be used as data without waiving credentials.
- Structured output separates documentary claims, project facts and visibly inferred advice. Validate schema, supplied-reference membership, exact spans/locators/version/current authority before history/checkpoint writes; construct citation URLs/IDs server-side. Invalid citations abstain, malformed output fails, access/credential violations block. Preserve all incurred/uncertain charges and do not automatically regenerate rejected answers.

## Remaining acceptance

- [ ] Complete shared/private review races, safe older-index retention and idempotent processing after review.
- [ ] Complete rule-update queue rescans, stale-assessment invalidation, source/authority-change dependent summary/citation invalidation and restore fencing.
- [ ] Verify every hosted role including embeddings, summaries and offline judges, blocked chat/generated text propagation and no rejected-output persistence.
- [ ] Verify cross-user isolation, shared catalog quarantine/operator boundaries and rule changes/revocation/context changes during waits, recovery and release.
- [ ] Finish audit/recovery/retention workflows and private hosted-indexing integration.
- [ ] Report detection/false-positive/overhead outcomes alongside the full answer/citation/abstention/privacy evaluation. Preserve 150 scenarios, 100/50 development/held-out and separate 30-output human reviews. No guard/judge bypass for evaluation.

Current tests use controlled disposable data and mocked provider HTTP. They do not guarantee complete detection or semantic faithfulness. See [rules](../../rules.md), [tasks](../../tasks.md) and [current report](../../reports/2026-11-01-personal-projects-checkpoint.md).
