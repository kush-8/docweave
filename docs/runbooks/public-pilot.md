# Frozen public retrieval pilot

This operator tool implements the approved public/synthetic fixture pilot. The user authorized a separate US$1 lifetime maximum; the original synthetic compatibility probes retain their US$0.25 cap. Both count against their workspace monthly allocation and the existing US$20 application ceiling. Reservations remain conservative retained amounts, not confirmed invoices. Private Gemini processing and ordinary project hosted profiles remain disabled.

## Run and recover

After migrating preserved development to `0012_public_pilot_budget`, run from the repository root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'backend/src'
.\backend\.venv\Scripts\python.exe -m docweave.evaluation.public_pilot
```

The CLI accepts no document, question, project URL or arbitrary file argument. It reads keys privately from the ignored `.env`. Its target guard permits only the preserved local development migration login; runtime RLS queries use the separate runtime login. Never run paid work against the disposable service.

Only the pinned manifest, document bytes and dataset bytes can supply model input. Query IDs resolve to frozen questions; document IDs resolve to exact prepared spans. Reranking accepts currently authorized indexed candidates only when their version IDs, titles and exact quotes match those public fixtures. Extra candidate fields are not sent. Initial setup creates a dedicated operator context; resume does not restore revoked grants, consent or sources.

Each canonical request is hash-bound to its disabled profile, scope, token bounds and `public_fixture` purpose. A claim and financial uncertainty commit before HTTP. Known validated results are reused across configurations and resume; unresolved or rejected operations cannot silently repeat paid work. Do not delete financial history or consumed registrations to retry. A failed/unknown operation requires operator investigation rather than automatic regeneration.

The actual provider call uses no retries, redirects or environment proxies. Compressed responses are refused before decoding; body size, exact model, IDs, usage and vector shape/norm are validated. Scope and consent are rechecked after quota pacing, immediately before HTTP and before releasing cached or fresh evidence. A post-dispatch revocation can block release while retaining incurred/uncertain cost.

## Inputs, budgets and interpretation

The corpus is the frozen synthetic runbook, dated rolling FastAPI tutorial and PostgreSQL 17 HBA text fixture, with their existing provenance/licenses. It contains no PostgreSQL 15 approval; the version control observes actual eligible indexed target metadata and requires zero compatible chunks rather than inferring a pass from its question label.

The operator publishes real 768-dimensional Gemini Embedding2 vectors through the normal atomic scoped-index functions. Runtime queries execute native full-text, authorized-statistics SQL BM25, filtered exact distance and shared HNSW. All four single-channel baselines and four hybrids run without/with the same Groq 20B reranker. RRF uses k=60; each channel supplies at most 30 candidates. Final evidence contains at most 8 whole chunks/6000 literal evidence tokens using pinned tiktoken 0.12.0/o200k_harmony. Role tags inside evidence remain ordinary text.

Groq's documented free plan has an8000-token/minute limit. At most 20 high-ranked whole candidates fit within 3000 serialized-request tokens, including query/schema/framing, with 4096 completion tokens reserved. Oversized candidates are omitted rather than silently truncating their quote/span. The report records actual rerank input IDs. New calls pace from observed remaining-token/reset headers, with conservative fallback; waits are split into at-most 30-second intervals. This controls quota without paid retries. See [Groq limits](https://console.groq.com/docs/rate-limits).

The ignored report is `backend/eval/reports/public-pilot-v1.json`. It records every configuration and mode, supporting recall in final 8, denial/version/no-evidence controls, actual SQL plans/timings, ANN recall/underfill, selected spans/tokens, generation/corpus/dataset hashes, implementation path/content fingerprints, build measurements and retained cost. Identical requests share durable results, so finalization latency can mix fresh dispatch, quota waiting and cache reuse; do not interpret those values as a controlled model-speed comparison.

At least one live configuration must support 9/10 answerable development questions and pass all controls. Failed variants remain visible. Human label review is pending; this small retrieval pilot does not establish answer correctness, faithfulness, a held-out release gate or a production default. Conversations and full answer/memory evaluation remain later roadmap work.

## Measured results — 2026-10-31

The live gate passed. All 13 scenarios ran through all 16 configuration/mode combinations. The published index contains 44 chunks across the three frozen documents; the shared HNSW index measured 188416 bytes. The report's source fingerprint still matches the audited working implementation, and every released quote matches its exact frozen-file span.

| Configuration | Without reranking: supported / controls | With reranking: supported / controls |
| --- | --- | --- |
| Native only | 3/10 / pass | 3/10 / pass |
| BM25 only | 10/10 / fail | 9/10 / pass |
| Exact only | 10/10 / fail | 10/10 / pass |
| HNSW only | 10/10 / fail | 10/10 / pass |
| Native + exact | 10/10 / fail | 10/10 / pass |
| Native + HNSW | 10/10 / fail | 10/10 / pass |
| BM25 + exact | 10/10 / fail | 10/10 / pass |
| BM25 + HNSW | 10/10 / fail | 10/10 / pass |

Seven reranked variants meet the at least 9/10 gate and all controls. The other variants remain failed: lexical native recall is insufficient, and the non-reranked BM25/vector/hybrid variants return evidence for the unsupported refund-policy question. Every variant denied the synthetic inaccessible collection and returned no PostgreSQL 15 evidence after observing zero eligible compatible chunks. No production default was selected.

The public ledger has 91 successful one-time operations with **US$0.4882432** conservatively retained. The separate synthetic ledger remains 4 operations/US$0.0364544. These are retained maxima, not confirmed bills. All hosted profiles remain disabled/account-unverified/capability-unverified for ordinary project processing. This explicitly approved frozen-input operator pilot does not implement the planned arbitrary-document quarantine, review or credential-scanning gate.

## Verification

Before the live run, the serial backend suite passed 595 tests with warnings as errors; lockfile, CLI help and development model/schema comparison passed. Independent review findings received observed failing regressions and fixes: authority is rechecked after pacing, and version controls observe the actual authorized index. Earlier isolated mocked runs exercise all configurations and resume without another provider request. The live report and persistent ledger were independently audited for source hashes, exact spans, limits, accepted variants and retained cost. Human labels, billing and full answer quality remain unverified.
