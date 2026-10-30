# DocWeave — Engineering Rules

Status: Backend foundational slices and a separate frontend preview exist. Backend RAG/evaluation planning reconciled 2026-10-30; frontend integration remains deferred.

## Read order and authority

Start with [memory.md](memory.md), then [PRD.md](PRD.md) and this file. Read [architecture.md](architecture.md) before backend/data/auth/provider/memory/evaluation changes. Read [design.md](design.md) before frontend/flow/theme changes. Follow [tasks.md](tasks.md) for execution order.

Direct user instructions take precedence. PRD owns product scope; architecture owns technical behavior; design owns frontend; tasks owns task state. Memory is a concise handoff and cannot override those documents. Fix contradictions at their authoritative source and update affected references together.

Current scope confirmed 2026-10-30: work on backend only, on `main`; frontend implementation/integration remains deferred. Groq serves all current hosted LLM roles, with Gemini permitted only for embeddings. Build both native full-text/BM25 and exact/HNSW retrieval paths for end-to-end RAG evaluation before choosing defaults. The future provider-selecting LLM gateway is outside this release. This supersedes earlier Gemini-reranking/three-answer-provider requirements, not historical implementation evidence.

Initial scaffold authorization was followed by the scoped backend/preview work recorded in tasks.md and memory.md. Continue the user's current authorized task and preserve pending changes; planning checkboxes alone do not authorize unrelated implementation, account changes, paid calls or deployment.

## Security and privacy invariants

- Workspace is the tenant. Authorize every operation against identity, tenant membership, resource ownership, roles, collection grants, and current processing policy; opaque IDs are never authorization.
- Conversations are author-private and project-bound. Apply policy to listing, titles, turns, citations, graph checkpoints, intermediate writes, summaries, background work, and history—not only retrieval.
- Google/GitHub/email accounts use verified identity-provider flows. Preserve issuer/subject identity, explicit secure linking, recipient-bound invitations, and last-owner protection.
- Require approvals for the actual processors of private project/doc/conversation content: Gemini for embeddings and Groq for LLM roles, including offline judges. Private identifier lookups need explicit discovery consent; raw configs/credentials/private URLs do not leave through lookup.
- Treat documents, project context, messages, summaries, and model output as untrusted. Models have no authorization-changing, browsing, shell, or deployment tools.
- GitHub repository access is separate from login, user-owned, read-only, and selected-repository scoped. Contents read is broader than filenames; enforce the application's file allowlist without pretending GitHub enforces it.
- Require current actor/viewer upstream access as well as DocWeave policy for private repo-derived context, including retained scans, summaries/checkpoints, labels, and jobs. No installation-token or workspace-owner bypass.
- Parse approved metadata statically at one commit. No cloning, installation, config evaluation, private-index authentication, unrestricted includes, submodule/symlink traversal, or code ingestion. Preserve partial/unsupported status, unknown role/directness, and declaration/resolution/selection provenance; constraint-only entries do not create selected dependencies.
- Resolve docs catalog-first. Approve new origin/path scopes and version fallbacks before import; user review cannot promote global catalog trust or override SSRF/robots/quotas. Apply rescans only after reviewed diffs.
- Revalidate external-call/result boundaries after queue waits. Revoked/deleted context pauses dependent conversations; contaminated memory cannot be copied into a new thread.
- Keep secrets backend-only and outside version control. Safe logs/audit omit raw content and credentials. Respect deletion across live data, checkpoints/writes, backups, and restored state.

## Reliability and cost invariants

- Keep one modular backend and separate ingestion/turn worker queues. Catalog technologies do not prescribe runtime dependencies.
- Commit accepted work durably; preserve idempotency and one active turn/conversation. Never claim that application deduplication guarantees provider exactly-once billing.
- Distinguish known failures from uncertain provider execution. A checkpoint replay or browser reload must not silently repeat a paid request.
- Atomically reserve both workspace and global budget before every paid role, including summaries/query resolution/probes. Unknown prices disable a profile; unknown execution retains conservative charges.
- Keep each conversation's provider fixed. Local inference, another provider, or unrecorded HF routing is not an automatic fallback.
- Bound model-visible context with summarization; retain authorized transcripts. No arbitrary conversation turn-count cutoff. Summaries/prior answers are context, not documentary evidence.
- Stage index/version replacements, then activate atomically. Keep prior good data on failed updates; tombstones prevent retries/re-index/restore from resurrecting deletions.

## Structured prompt-writing rule

Every LLM prompt must clearly separate application-controlled rules, the task, untrusted input data, the user query and the output contract. This applies to answering, reranking, query resolution, summarization and offline judging.

```text
SYSTEM — application-controlled
  task
  rules
  output_contract

USER — serialized data envelope
  query
  project_context
  conversation_context
  evidence
```

Use only roles supported by the verified profile and JSON-encode data values. Never interpolate documents, queries, history or summaries into trusted instructions or let their content define message roles. Preserve evidence/version/provenance IDs; owner-reviewed documents remain untrusted evidence. Use shared prompt builders and version-controlled templates, record prompt versions in operations/evaluation reports, and test embedded delimiters, fake roles and instruction overrides as literal data. Count schema/framing against existing token budgets. Structured formatting does not establish factual correctness or eliminate prompt injection.

## RAG guardrail policy — confirmed 2026-10-31

The [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md) is approved direction, not implemented protection. Reuse current access, ingestion, consent and budget controls; add deterministic checks rather than live guard-model calls. General content moderation and semantic caching are outside this scope.

- Quarantine document versions flagged for instruction overrides, role spoofing or requests to expose system instructions/secrets; workspace owners review them. Block similarly flagged chat messages before hosted calls.
- Detect strong credential/private-key/token/authorization/connection-string formats, with explicit placeholder handling rather than broad entropy guesses. Block external use until content is sanitized; do not auto-redact, mutate original text or permit review to waive this block.
- Bind assessments/reviews to exact version, content hash, parser configuration and rule revision. Enforce them in indexing, retrieval, provider dispatch and evidence release; a status label alone is insufficient. Preserve an older eligible index when a replacement is held.
- Reviews require current resource/owner authority, CSRF and expected revisions, with content-free audit. They cannot grant source trust, consent, budget or broader access. After rule changes, rescan existing versions; clean versions resume and flagged versions require current review.
- Use provenance-aware preflight across every hosted role, including offline judges. Do not blanket-reject an assembled prompt because explicitly reviewed evidence contains a flagged phrase. Recheck dependent memory/citations when eligibility changes.
- Require structured documentation/project-context/inferred-advice blocks; validate references, spans and access before history/checkpoint writes. Render citations server-side. Invalid citations abstain; malformed output fails operationally; credentials/access violations block release. Do not automatically regenerate rejected output; retain incurred-cost accounting.

## Implementation and evidence

Use existing/platform/library behavior before adding abstractions or dependencies. Maintain contracts, migrations, OpenAPI, accessible UI states, and recovery instructions with the behavior they describe. Patch shared causes and affected callers together.

Use uv for backend dependency management and npm for the frontend. Add or update dependencies only when the current task needs them; do not install the future stack upfront. Keep manifests and lockfiles in sync when dependencies change, and run the relevant checks.

Each task follows a meaningful failing test -> minimal implementation -> relevant verification cycle. Prefer behavioral/security/failure tests over mirrored implementation tests. Keep deterministic CI free of paid keys; use explicit budget-reserved live integration runs to prove current provider behavior.

Record corpus/config/prompt/model/backend/tokenizer/dataset versions. Keep development, calibration, and held-out release evidence separate. Labels and generated-output human reviews are different work.

RAG evaluation must exercise the actual backend answer workflow and score correctness, faithfulness, relevance, citation support, abstention, memory/privacy behavior, latency and cost alongside retrieval diagnostics. No configuration may trade unauthorized/incompatible-version evidence for quality. Verify exact/HNSW query plans and BM25 corpus-statistics isolation; keep all four hybrid comparisons on identical inputs/settings. Initial ten-question smoke results do not establish the production winner. Configure evaluator providers explicitly; judge calls use the same reservation/consent boundaries as other hosted roles.

Every milestone includes the builder's brief explanation of the main choices and one relevant failure walkthrough. A passing application test alone does not satisfy the learning goal.

Only the user can approve reductions to accepted scope or release criteria. Record owner/date/reason/evidence for such a revision. Reporting a failed target never needs permission; silently lowering the bar is forbidden.

## Status and handoff

Distinguish confirmed direction, engineering defaults, public-doc candidates, account-verified compatibility, implemented behavior, and measured results. Do not mark all 29 sources supported, security proven, models available, or performance achieved without the task's evidence.

After a substantive session, update memory with actual changes/checks, remaining risks, and next unfinished task. Keep the six planning filenames in `docs/` with their existing responsibilities. [README.md](../README.md) owns the physical folder map. Keep backend-owned catalog, evaluation, and infrastructure assets under `backend/`; frontend code consumes HTTP APIs rather than importing them. The eventual repository is independent of the portfolio parent; Git initialization remains a separate step.

The written-design direction is confirmed. The implementation plan in tasks is documentation; its unchecked items do not authorize executing them.
