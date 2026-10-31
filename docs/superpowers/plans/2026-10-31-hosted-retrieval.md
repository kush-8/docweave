# Task 3C: hosted retrieval

The user authorized the backend roadmap, requested simple code, and reserved architectural decisions for review. Task 3B is checkpoint `b942fe0`. Keep the frontend deferred and commits local.

## Scope and constraints

Reach the existing budget/profile migration, current policy functions, ingestion/index callers, retrieval and evaluator, operator configuration, fixtures, tests and runbooks. Reuse PostgreSQL, HTTPX2, the durable queue and exact Decimal accounting. No provider SDK or automatic routing is needed. Preserve old profile/charge identities, searchable versions and private data. No paid dispatch against the disposable database.

- [x] Verify API-key authentication using model metadata only; Gemini Embedding 2 and both Groq GPT-OSS candidates are listed. No inference capability is inferred from that result.
- [x] Restore development access using the explicitly approved repair, with private database/login backups, unchanged original row counts and three restricted logins. Upgrade the preserved development volume to tested `0009_retrieval`; its queue is installed and empty.
- [x] Confirm operator-only synthetic probe admission and Gemini billing status. The user approved the fixed-synthetic path and confirmed free tier/billing unknown. Private Gemini processing stays disabled. First probes must have a durable total US$0.25 cap; unverified profiles must never receive project content.
- [ ] Reconcile eligibility to Gemini embeddings plus Groq LLM roles. Write failing role/consent regressions first; preserve historical profiles and ledger records.
- [ ] Add a private dispatch journal bound to reservation, immutable request digest and current source/grant/processor context. Test concurrent claims, uncertain commit/completion, timeout, revocation after waits and resume without paid replay before implementing it. Use narrow functions, not runtime table DML.
- [ ] Add fixed Gemini/Groq HTTP requests with retries off, bounded responses, exact-model identity, usage and ranking validation. Gemini Embedding 2 uses prompt prefixes instead of `task_type`, 768 auto-normalized dimensions and an 8192-token model limit. Verify tokenization and total billed Groq reasoning/output bounds before enablement.
- [ ] Add deterministic deduplication/RRF (k=60, 30/channel), at most 20 rerank inputs and at most eight exact-span chunks/6000 evidence tokens. Test boundaries and current authority before egress and release.
- [ ] Run synthetic compatibility probes through persistent reservations and the journal; record redacted configuration, rates, bounds, observed usage, supported schemas and failures. Do not automatically repeat uncertain requests. Keep unsupported profiles disabled.
- [ ] Embed the frozen corpus and queries, preserve hashes/configuration/provenance, and execute all baselines/four hybrids without and with fixed reranking. Record actual plans, cost, latency, final-eight support recall and denied/version/no-evidence cases. At least one configuration needs 9/10 support recall; ten development questions do not establish a production default.
- [ ] Run focused tests, then the backend suite with warnings as errors. Get the required independent review, resolve findings and commit a separate Task 3C checkpoint with honest remaining limitations.

## Primary contracts checked on 2026-10-31

- [Gemini embedding formats, dimensions and model limits](https://ai.google.dev/gemini-api/docs/embeddings): Embedding 2 query/document prefixes; no Embedding 1 task field or vector reuse.
- [Gemini prices and data-use tiers](https://ai.google.dev/gemini-api/docs/pricing): standard text US$0.20/million; free-tier inputs may improve products. Billing status still needs the operator's answer.
- [Groq GPT-OSS 20B](https://console.groq.com/docs/model/openai/gpt-oss-20b): US$0.075 input/US$0.30 output per million; 131072 context, 65536 output maximum. Adapter limits will be much smaller.
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs) and [API reference](https://console.groq.com/docs/api-reference): strict JSON schema, required fields/additionalProperties=false, explicit completion limit and low reasoning effort. Neither advertised support nor key authentication substitutes for account-level probes.

## Verification so far

The full backend suite passed 532 tests with warnings as errors before the final review fix. The reviewer found that deleting a consumed request registration could erase lifetime-cap accounting. A new regression failed first; consumed registrations are now immutable under the shared budget lock. After rebuilding only the disposable tmpfs service, 113 relevant tests passed, including migrations/downgrades, model comparison, budgets, profiles, probes and fusion. Development then migrated to `0011_compatibility_probes` without resetting its preserved volume.

Normal project dispatch, exact-model adapters and the live pilot remain unimplemented. The request registry contains only hashes and token bounds; the forthcoming operator runner must derive them exclusively from fixed synthetic factories and verify the exact serialized body before HTTP dispatch. The database cannot attest to arbitrary client text by itself. No inference call has been made. External checkpoint `b4f62e8` captured earlier work and added the structured-prompt/RAG guardrail direction; preserve it and apply those requirements to forthcoming adapters.

Task 3B: 505 backend tests passed with warnings as errors; 13 evaluator tests passed again after metadata-only reporting changes. Development repair: one guarded disposable regression passed; approved live repair preserved original table counts, authenticated the three non-superuser/non-bypass logins, reached `0009_retrieval` and found zero queued jobs. Secrets and backups remain ignored.
