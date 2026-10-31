# Approved frozen public retrieval pilot

The user approved the operator-only frozen public/synthetic fixture pilot on 2026-10-31, with a separate US$1 lifetime cap. They subsequently asked to complete this current task. The broader roadmap goal remains cleared. Preserve the external responsibility-separation work (checkpoint `2adda62`) and use its layer boundaries. Private Gemini processing remains disabled with free-tier/billing-unknown credentials.

## Acceptance and progress

- [x] Bind input to the exact frozen manifest, document bytes and question-file hashes; accept identifiers/spans rather than arbitrary private text.
- [x] Preserve US$0.25 synthetic and US$1 public-fixture lifetime buckets, monthly workspace allocations and US$20 global ceiling. Consumed request classifications cannot be edited or removed.
- [x] Reuse disabled profiles, persistent reservations and one-time dispatch claims. Unknown outcomes/cancellation/commit acknowledgements cannot trigger automatic paid replay.
- [x] Enforce current grants, consent, source/version state before egress, after pacing and on cached result release. Initial preparation is idempotent and does not restore revoked authority on resume.
- [x] Publish actual Gemini vectors through the normal scoped atomic index functions; exercise actual runtime RLS, native full-text, SQL BM25, exact distance and HNSW queries.
- [x] Add the pinned GPT-OSS Harmony tokenizer for literal evidence. RRF k=60 remains unchanged; at most 20 whole chunks enter reranking within 3000 serialized input tokens and4096 completion tokens; final evidence stays at most 8 chunks/6000 evidence tokens.
- [x] Preserve structured trusted-system/JSON-data prompts, validate exact IDs/outputs and pace new requests using observed Groq token quota headers. Keep retries off.
- [x] Execute all 8 registered configurations without/with fixed Groq reranking in the mocked end-to-end protocol. Record plans, candidate/selected IDs, token counts, supported questions, no-evidence/denied/version controls, hashes, costs, timings and failed variants.
- [x] Resolve fresh review findings after observed failing regressions: authority after pacing; version-control results must observe actual eligible index metadata. Final review found no additional issues.
- [x] Finish serial full-suite verification, migrate preserved development to0012 and run the live pilot under its separate cap.
- [x] At least one measured live configuration must support 9/10 answerable questions and pass all controls. Preserve every failed variant; do not infer a production winner or answer correctness from this retrieval pilot.
- [x] Update runbooks/status with actual measured evidence and create a local checkpoint containing only this task's files.

## Evidence so far

The layered baseline was externally verified at586 tests. A serial run with this pilot passed 593 tests before final free-plan handling. The final focused set passed 37 tests. The final serial full suite passed 595 tests with warnings as errors. Lockfile, CLI help and preserved development model/schema checks passed. One earlier full run was invalidated by an accidentally overlapping disposable-database check; that run is not verification evidence.

Live evidence: 13 scenarios x16 variants, 44 published chunks, 188416-byte shared HNSW index. All four reranked hybrids and the exact/HNSW reranked baselines supported 10/10 questions; BM25 reranked supported 9/10. All seven passed controls. Native-only reached 3/10; other variants without reranking failed the no-evidence control. The public ledger has 91 successful operations and US$0.4882432 conservatively retained; synthetic remains 4 operations/US$0.0364544. Source fingerprint, exact spans, final limits, actual controls and ledger were audited after execution. The [runbook](../../runbooks/public-pilot.md) retains results and interpretation. Human labels, invoice billing, private processing and full answer quality remain unverified. The local checkpoint delivers this task; the broader roadmap remains cleared.

Primary contracts: [GPT-OSS tokenizer mapping in pinned tiktoken 0.12.0](https://github.com/openai/tiktoken/blob/0.12.0/tiktoken/model.py), [Groq account rate limits and response headers](https://console.groq.com/docs/rate-limits), [Gemini Embedding2 limits](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2). Request-byte guards do not claim to be a Gemini tokenizer. The complete input window is reserved conservatively and profiles remain disabled for ordinary project processing.

## Failure walkthrough

A durable claim may commit before quota pacing. Revoking collection consent during that wait must block the pending HTTP call. A regression first reached the forbidden mocked provider; the fix adds a fresh authorization check after pacing. The claim still retains conservative uncertainty, and resume cannot replay it. An independent version regression changes eligible indexed target metadata; the evaluator now detects that change instead of declaring PostgreSQL 15 unavailable solely from a scenario label.
