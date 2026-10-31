# Hosted compatibility checks

Task 3C has an operator-only fixed synthetic runner. It accepts four built-in requests, not project text, uploads, URLs or client-defined prompts. Its development target guard allows only the migration login on `127.0.0.1:55432/docweave`. Never use the disposable database for paid work.

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'backend/src'
.\backend\.venv\Scripts\python.exe -m docweave.compatibility
.\backend\.venv\Scripts\python.exe -m docweave.compatibility --run
```

The first command prepares a dedicated synthetic actor/workspace/project, disabled profiles and hash-bound requests without inference. `--run` uses the ignored `.env` keys without printing them. Each exact request receives a persistent reservation and a one-time claim before HTTP. Concurrent callers, cancellation, lost commit acknowledgements and resume cannot automatically repeat paid work. A response or transport failure retains the conservative maximum until billing is reconciled; never delete financial history to retry. Consumed registrations are immutable and share a US$0.25 lifetime maximum across workspaces. The monthly workspace allocation is US$0.25 and the application ceiling remains US$20.

Requests use explicit timeouts, no SDK/transport retries, no environment proxies, no redirects and identity encoding. Compressed responses are rejected before decoding; response size and JSON/model/ranking/vector fields are checked. Groq reranking separates trusted system instructions from a JSON data envelope, with no tools, strict output schema, low reasoning effort and 4096 completion tokens. Gemini Embedding 2 uses query/document prefixes and 768 dimensions. This is not a general project dispatch API or a claim that prompt formatting prevents injection.

## Observed development results, 2026-10-31

All four initial requests succeeded. Gemini query/document vectors had 768 dimensions and norms approximately 1.0000003/0.9999999. Groq 20B returned the expected ID with 469 input, 60 completion and 24 reported reasoning tokens; Groq 120B returned the expected ID with 469 input, 63 completion and 20 reported reasoning tokens. Full completion counts are retained alongside reasoning metadata; provider billing interpretation is still unverified.

The ledger retains **US$0.0364544**, a conservative reservation rather than confirmed invoice cost. The ignored report is `backend/eval/reports/compatibility-v1.json`; result metadata is also durable in PostgreSQL. All profiles remain disabled and account/capability flags remain unverified. Gemini free-tier/billing-unknown status does not authorize private processing.

Rates checked against [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Groq 20B](https://console.groq.com/docs/model/openai/gpt-oss-20b) and [Groq 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b): respectively US$0.20 input; US$0.075 input/US$0.30 output; and US$0.15 input/US$0.60 output per million tokens. The first probes reserve the entire advertised input window, not a provisional tokenizer estimate.

The user separately approved the [frozen public/synthetic fixture pilot](public-pilot.md) with a distinct US$1 maximum. Its live run passed: all four reranked hybrids supported 10/10 questions and passed controls, with US$0.4882432 conservatively retained. The GPT-OSS Harmony tokenizer enforces the evidence/request limits. Ordinary project dispatch, private Gemini processing, billing verification and full answer quality remain unfinished. The existing synthetic-only exception is unchanged.
