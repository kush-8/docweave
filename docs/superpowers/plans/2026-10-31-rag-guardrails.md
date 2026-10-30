# Backend RAG Guardrails Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans or superpowers:subagent-driven-development when implementation is authorized. Follow the unchecked steps below; this document does not claim implemented protection.

**Goal:** Add deterministic RAG guardrails and a project-wide structured-prompt rule while preserving tenant isolation, source provenance, private memory and cost controls.

**Architecture:** Reuse the modular backend, PostgreSQL policies/private functions, Procrastinate ingestion queue and existing provider admission boundary. Version-bound assessments and owner reviews gate model use; shared prompt builders and structured answer validation guard model boundaries.

**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLAlchemy/Alembic, PostgreSQL/pgvector, Procrastinate and pytest. No new guardrails framework or hosted detector is selected.

**Spec:** [Engineering rules](../../rules.md#structured-prompt-writing-rule), [architecture](../../architecture.md#structured-prompts-and-rag-guardrails), [product requirements](../../PRD.md) and the decisions below. Confirmed 2026-10-31; documentation only in this session.

## Global constraints and confirmed decisions

- Backend only on `main`; preserve concurrent work and completed 3A/3B evidence. Frontend implementation is deferred.
- Groq serves all hosted LLM roles; Gemini is the embedding-only exception. Every hosted call retains current authorization, consent, budget, dispatch and uncertainty controls.
- Use deterministic RAG protections first. General moderation, semantic caching, automatic redaction and live guard-model calls are outside scope.
- Quarantine injection-flagged documents for workspace-owner review. Block similarly flagged chat before any hosted call, including summaries/query resolution.
- Detect strong credential formats rather than broad entropy guesses. Credential blocks cannot be waived through review; sanitized replacement content is required.
- Bind scan/review eligibility to exact version, content hash, parser configuration and rule revision. Keep original snapshots/locators and older eligible searchable versions.
- Updated rules require existing versions to be rescanned before model use. Clean versions resume; flagged versions require current review.
- Use structured evidence links internally and render the existing public text/citations contract. Preserve current token/attempt limits, source/deletion policy and the 150-scenario/100-development/50-held-out protocol with separate 30-output human reviews.

## Structured prompt-writing contract

Every LLM prompt separates trusted rules/task/output requirements from query and untrusted data. Use only verified profile-supported message roles:

```text
SYSTEM — application-controlled
  task
  rules
  output_contract

USER — JSON-serialized data envelope
  query
  project_context
  conversation_context
  evidence
```

Apply shared, version-controlled builders to answers, reranking, query resolution, summaries and offline judges. JSON-encode values rather than interpolating content into trusted rules. Embedded role tags, delimiters and instruction text remain data; model content cannot create roles or authorize actions. Keep source/version/provenance IDs, count framing/schema tokens and record prompt versions in operations/evaluation reports. Absent input categories are explicitly empty rather than being mixed into other categories. Preserve verified model-specific embedding configuration independently.

Approved documents remain untrusted. Provider preflight inspects segment provenance rather than blanket-rejecting a complete prompt containing an owner-reviewed document's flagged phrase. Helpers must not turn untrusted content into trusted system instructions. Credential checks still apply to all outgoing text.

## Review focus

- The current ingestion `quarantined` status is preparation, not an enforced review verdict; status-only changes must not permit indexing/retrieval.
- Prepared and searchable snapshots differ; holding a replacement must not wrongly release it or disable a still-eligible older index.
- Review decisions can race owner revocation, content changes, rule updates and deletion; stale decisions never activate content.
- Legitimate security documentation contains attack examples; owner approval must permit its untrusted use without disabling credential/access checks.
- Framework history/checkpoints can persist intermediate model output; validate before any such write and retain accounting even when output is rejected.

## Checkpoint 1 — Document assessments, owner review and model-use gates

**Files/responsibilities:** Add `backend/src/docweave/guardrails.py` for bounded scanners and assessment/review services; extend domain models, a new migration after the current schema, ingestion/retrieval/worker integration and API schemas. Add `backend/tests/test_guardrails.py` and extend ingestion/retrieval authorization tests. Reconcile OpenAPI only during implementation.

**Interfaces:** Internal version-bound assessments; owner-only `GET`/`PUT /documents/{id}/versions/{version_id}/guard-review`; safe per-version assessment/review metadata on existing document/source/job views.

- [ ] Write failing tests for instruction override/role-spoofing/secret-exposure signatures and legitimate examples; strong key/token/header/credential-bearing URI formats and explicit placeholders; scan-only normalization preserving immutable text/hash/locators.
- [ ] Observe those failures, then implement bounded versioned rules. Store rule IDs/safe findings without matched credentials; fail closed for missing/failed/currently held assessments.
- [ ] Add failing integration tests, then persist assessments/reviews against exact version/hash/parser/rule revision with tenant RLS and narrow service functions. Check eligibility at index input/insertion/activation, chunk retrieval and evidence release, including the actual indexed version.
- [ ] Add owner-authorized review reads with bounded snapshot-text pages and revision-checked decisions, CSRF and content-free audit. Test cross-tenant/nonowner denial, post-lock ownership loss, stale hashes/rules/revisions and deletion. Review grants no source/processor/budget authority and cannot waive credentials.
- [ ] Test an approved injection-flagged example remaining untrusted, safe older-index retention and A→B→A version reuse. On review release, enqueue remaining eligible processing idempotently without replaying uncertain paid work.
- [ ] Reuse the ingestion queue for rule-update rescans. Hold affected versions until rescanned; clean versions resume and flagged versions require current review. Fence dependent memory/citations when eligibility changes; restore cannot bypass current policy.
- [ ] Run relevant guardrail/ingestion/retrieval/database checks on guarded disposable targets. Record actual results and update runbooks; do not mark protection complete from unit scanners alone.

## Checkpoint 2 — Shared prompts, provider preflight and validated answers

**Files/responsibilities:** Extend the guardrails module, provider dispatch, Task 3C reranking and Task 4 workflow/memory/answer schemas. Keep prompt construction shared by role and test it without paid keys.

**Interfaces:** Versioned structured prompt builders; provenance-aware provider preflight; internal documentation/project-context/inferred-advice blocks rendered into existing public text/citations.

- [ ] Write failing tests for every LLM role's section/role separation, JSON escaping, fake system messages/delimiters, evidence provenance and token/framing bounds; implement shared builders to satisfy them.
- [ ] Test that flagged chat and generated query/summary text stop before subsequent hosted calls, and blocked content does not enter model memory. Input/resource validation and turn admission remain distinct from policy blocks.
- [ ] Before every provider-bound role, including embeddings/offline judging, revalidate credentials, resource/source/assessment state, processor consent and budget. Test reviewed evidence is not blanket-reblocked while credentials remain non-waivable. Assert forbidden payloads never reach fake adapters.
- [ ] Validate structured answer blocks: documentation claims reference supplied evidence; project statements reference supplied context; advice is visibly inferred. Verify schema/reference membership, exact quotes/locators, versions and current access, then construct citation IDs/URLs server-side.
- [ ] Test validation before history/checkpoint writes. Invalid citations produce safe abstention; malformed output is operational failure; credential/access violations block release. Do not automatically regenerate rejected output or erase incurred charges; preserve uncertain-execution handling.
- [ ] Run relevant provider/workflow/memory/recovery tests once those modules exist; document which checks are fake-provider regressions versus live evidence.

## Checkpoint 3 — Evaluation, rollout and documentation

**Files/responsibilities:** Extend the existing evaluation runner/protocol tests and development fixtures; synchronize rules/architecture/tasks/API notes/runbooks and handoff memory with actual implementation evidence.

- [ ] Add deterministic boundary cases for prompt injection, legitimate examples, credentials, owner-review races, rule/hash changes, stale approvals, older indexes, quarantine/deletion/revocation, structured citations and rejected-output persistence.
- [ ] Report detection outcomes/false positives and overhead alongside end-to-end correctness, faithfulness, citation support, abstention and privacy. Keep the existing 150-scenario split/human calibration protocol; boundary regressions may live outside that scored benchmark. No guard or judge bypass is introduced for evaluation.
- [ ] Roll out document gates before hosted corpus work in 3C; integrate chat/helper/answer gates with Task 4 and judging with Task 10. Default existing unassessed versions to held model use, enqueue bounded scans, and record any remaining blockers.
- [ ] Reconcile public schemas/routes during implementation, update all owning docs and run the relevant checks before marking a checkpoint complete.

## Verification boundary

This is an approved implementation direction recorded as documentation, not executed guardrail code. Pattern checks miss some attacks/secrets, and structural evidence links do not establish semantic truth. Record adversarial failures honestly; retain human calibration and existing mandatory security/release gates. No new framework, paid detector, provider access or performance result is claimed.
