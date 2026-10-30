# DocWeave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build the confirmed multi-tenant, evidence-grounded, conversational DocWeave release.
**Architecture:** One modular FastAPI backend, PostgreSQL/pgvector, durable ingestion/turn/scan jobs, protected LangGraph memory, and a React frontend. Build the backend small-corpus RAG workflow and its evaluation pipeline together; then extend source coverage and operations. Frontend implementation/integration remains deferred by the user.
**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/Alembic, PostgreSQL/pgvector/Procrastinate, LangGraph/LangChain, Keycloak, React/TypeScript/Vite, Docker Compose, pytest, Playwright, OpenTelemetry.
**Spec:** [PRD.md](PRD.md), [architecture.md](architecture.md), and frontend [design.md](design.md).
**Status:** Plan and GitHub extension reconciled on 2026-10-28. The frontend preview, tested API skeleton, and PostgreSQL/core-schema foundation are implemented as separately authorized slices. Complete authenticated product workflows remain unimplemented. No full-release task below is complete solely because its infrastructure exists.

On 2026-10-29, backend contract tests were added in `backend/tests/test_openapi.py`, with uv-locked dev dependencies. All 70 tests passed; 12 in-memory contract mutations were detected. This validates the draft contract only; the runtime/security/integration tests and task checkboxes below remain unfinished.

Frontend progress on 2026-10-29: a labeled synthetic Ask workbench now implements citation/evidence interaction, responsive shadcn sheets, Tailwind themes, provider selection, and draft/history protection. Build, lint, and 11 browser checks pass, including automated accessibility scans. This preview has no live backend integration and does not complete any full-release task below. See [workbench slice](superpowers/plans/2026-10-29-workbench.md) for scope and evidence.

The user then clarified that backend work must follow TDD and authorized every draft operation as an HTTP skeleton, with business logic, database and AI deferred. Tests were written and run first (75 runtime failures from the missing app; 70 contract checks passing), then the minimal FastAPI app was added. All 145 checks now pass with warnings treated as errors. Liveness returns 200, readiness 503, and the other 67 operations 501; runtime docs describe those actual responses. A temporary local Uvicorn check passed and was stopped. See the [skeleton plan](superpowers/plans/2026-10-29-api-skeleton.md). Authentication, request-body validation, persistence, and full Task 1 acceptance remain unimplemented; no full-release milestone is complete.

Database progress on 2026-10-29: implemented the user-approved [database foundation](superpowers/plans/2026-10-29-database-foundation.md): pinned PostgreSQL/pgvector Compose services, explicit Alembic migration, core models, SELECT-only runtime role, membership-backed RLS, and transaction-local sessions. Development is migrated at `0001_core` and survived restart; 51 database checks plus the existing 145 checks passed (196 total, warnings as errors). The disposable test service is separate from development and its target guard rejects query overrides. Authentication, application writes, full business authorization, and overall readiness remain deferred. See the [database runbook](runbooks/database.md). Task 1 remains incomplete.

Backend auth progress on 2026-10-30: the user authorized backend-only implementation. Added Authlib OIDC, browser-bound single-use state/nonce/S256 PKCE, issuer/subject provisioning, encrypted expiring PostgreSQL sessions, `/me`, logout and session/origin/CSRF dependencies, with narrow migration/grants. Local Keycloak/separate identity PostgreSQL/captured SMTP are configured; signed-token/runtime-role tests and a real local email/reset smoke verify the slice. Frontend auth, workspace/invitation/project operations and social-provider account checks remain future work. Full Task 1 is incomplete. See [auth plan/evidence](superpowers/plans/2026-10-30-auth.md) and [auth runbook](runbooks/auth.md).

Workspace backend slice completed 2026-10-30 under the user's instruction to continue backend-only: implemented POST/GET `/workspaces`, atomic owner membership, actor/resource-bound pagination and reusable current membership/owner guards on workspace child routes. Runtime domain DML remains denied; `0003_workspaces` adds narrow functions plus a membership-user index without broadening selected-tenant RLS. Invitations/member mutation/last-owner handling and project CRUD remain next slices; full Task 1 is incomplete. See [workspace plan/evidence](superpowers/plans/2026-10-30-workspaces.md) and [runbook](runbooks/workspaces.md).

Membership/invitation backend slice completed 2026-10-30: owner-only paginated lists, role changes/removal, 48-hour hashed single-use invitation creation/revocation/recipient acceptance, 409 last-owner protection under races and automatic pending-invite revocation when the issuer loses ownership. `0004_memberships` adds private invitation storage and narrow transactional functions; no general runtime domain DML is granted. Real held-lock tests verify expiry and owner authority after waits. Frontend, project CRUD, collection policy and full Task 1 remain incomplete. See [membership plan/evidence](superpowers/plans/2026-10-30-memberships.md) and [runbook](runbooks/memberships.md).

Manual project backend slice implemented 2026-10-30 on `main`: owner create/PATCH, member list/read, safe global project-ID resolution and project-child guards, encrypted scoped cursors, optimistic revisions and post-lock owner revalidation. Revision `0005_projects` adds owner-only default collection storage and private pending-documentation requests, created/updated atomically with manual context. Unapproved origins/versions stay pending; GitHub-reviewed input returns 501 with no writes. No import jobs, hosted calls, collection-grant API or complete Task 1 milestone is claimed. See [project plan/evidence](superpowers/plans/2026-10-30-projects.md) and [runbook](runbooks/projects.md).

Collection access/consent backend slice implemented 2026-10-30 on `main`: owner collection creation, grant-filtered cursor listing, owner grant read/complete replacement and separate project/collection processor-policy read/replacement. Revision `0006_collection_policy` keeps tenant grants/approvals private, uses current role/grant RLS and reconciles demotion/removal without permission resurrection. Immutable operator processor identities can be explicitly approved only when enabled; empty replacement revokes all. Consent does not enable inference, bypass budget admission or implement worker/history pausing. See [plan/evidence](superpowers/plans/2026-10-30-collection-policy.md) and [runbook](runbooks/collection-policy.md). Frontend, real provider/account verification and full Task 1 readiness remain unfinished.

Budget/profile backend slice implemented 2026-10-30 on `main`: immutable versioned profile records and public answer-profile listing, private exact-cost reservation/reconciliation, explicit operator monthly allocations and own-workspace/project usage. Revision `0007_budget` serializes financial changes with a shared advisory lock; retained uncertainty and confirmed charges count toward both tenant allocation and US$20 Asia/Calcutta ceiling. Replays preserve original intent/month/status; observed overruns are recorded and disable the profile. No live profiles/prices/account capabilities, paid calls, adapters or dispatch authority are claimed. See [plan/evidence](superpowers/plans/2026-10-30-budget.md) and [runbook](runbooks/budget.md). Next backend slice is the approved small-corpus ingestion path with explicit adapter/price verification before hosted work.

## Current backend task order — 2026-10-30

2026-10-31 checkpoint: Tasks 3A and 3B are implemented through deterministic/recorded-vector evaluation. The full backend suite passes 505 tests with warnings as errors. See [ingestion](runbooks/ingestion.md) and [retrieval](runbooks/retrieval.md). The evaluator CLI reports matching frozen corpus hashes, current scope and real exact/HNSW plans; it explicitly withholds semantic quality claims. The user chose operator seed SQL (owner API stays Task 7) and SQL BM25 with authorized corpus statistics. Next: 3C real adapters, profile/processor reconciliation, bounded dispatch/fusion/reranking and live compatibility/pilot evidence. The user is configuring keys and development DB access; no paid call has been made.

The user confirmed two lexical implementations (PostgreSQL native full-text and BM25), two vector strategies (filtered exact nearest neighbours and shared HNSW with database filtering/iterative scans), and an end-to-end RAG evaluation pipeline. Evaluate their four hybrid combinations before choosing production retrieval defaults. None of these paths or quality results is implemented yet.

| Order | Task | Deliverable |
| --- | --- | --- |
| 1 | 3A | Durable bounded TXT/Markdown ingestion and frozen FastAPI/PostgreSQL fixtures |
| 2 | 3B + 10 foundation | Tenant/version-scoped indexing, both lexical/vector strategies, and versioned evaluation cases/run reports |
| 3 | 3C + guardrail checkpoint | Version-bound scanning/owner review and provider preflight before hosted adapters, bounded hybrid retrieval and the pilot |
| 4 | 4 + 10 RAG pilot | Versioned structured prompts, validated Groq answers, private memory and end-to-end RAG evaluation |
| 5 | 6–7 backend | Read-only GitHub stack review, reviewed documentation discovery, version selection and rescan APIs |
| 6 | 8 | Remaining formats, full lifecycle and all 29 verified bounded documentation sources |
| 7 | 9 | Groq profile/adapter hardening across all hosted LLM roles |
| 8 | 10 release | Calibrated, frozen 150-scenario RAG benchmark and held-out quality gates |
| 9 | 11–12 backend | Operations, recovery/deletion/load drills and reproducible release evidence |

Task 5 and frontend portions of Tasks 6–8/12 remain in the full roadmap but are not active backend work or prerequisites for backend CLI evaluation. Tasks 1–2 have implemented slices documented above; remaining full-release acceptance and the processor-mapping follow-up below are still open. Exact model IDs below are verification candidates, not account-verified or measured choices.

## Future goal outside this release

After the core application workflow works and is evaluated, introduce an MCP server for authorized knowledge search and cited evidence retrieval, reusing the web application's backend retrieval and policy checks. See [Future goals](PRD.md#future-goals). This is not an active implementation task or a dependency of the current release; tool contracts, client authentication, and compatibility checks will be planned when scheduled.

The user also confirmed a future **LLM gateway** that chooses between providers. Do not build routing/gateway infrastructure now. Groq is the current release's sole hosted LLM provider; Gemini is the explicitly approved embedding-only exception. Earlier Gemini/Hugging Face answer-provider and three-provider comparison requirements are superseded for this release; historical profiles/ledger identities must remain intact.

## Global Constraints

- Workspace is the tenant; conversations are author-private and project-bound.
- Google, GitHub, verified email/password; owner-issued recipient-bound invitations.
- Gemini embeddings only; Groq-hosted LLMs for answers, reranking, required query resolution, summaries and offline judging. Candidate roles: `gemini-embedding-2` at 768 dimensions; Groq `openai/gpt-oss-120b` for answers/judging and the conversation's fixed answer model for summaries; Groq `openai/gpt-oss-20b` for reranking/query resolution. Verify before enabling.
- Implement native full-text and BM25 lexical retrieval plus exact and HNSW vector retrieval; select defaults from development RAG evaluation, never held-out tuning. Tenant isolation and version correctness are mandatory for every configuration.
- Each conversation fixes its answer provider; no silent fallback or local-inference substitution.
- Persist full transcripts; summarize model context; no arbitrary chat-length cutoff.
- Answer input ceiling 24,000 tokens, including at most 12,000 memory tokens, using the selected model tokenizer.
- Global US$20/month ceiling and operator-configured workspace caps; reserve every paid operation first.
- Match official docs to detected/selected versions where available; explicit unresolved-version and major/minor fallback review.
- All 29 catalog entries remain required; noncatalog sources require project/workspace review, not automatic global promotion.
- Optional user-owned read-only GitHub connection; private derived context requires current upstream actor/viewer access.
- Static Python/JavaScript/TypeScript manifests only; uv/npm/pnpm lock resolution; no source-code ingestion or execution.
- One repository/application per project; commit-pinned scans and explicitly reviewed rescan diffs.
- Light/dark toggle; device preference initially and per-device override.
- Immediate access revocation; local deletion within 24 running-service hours, backup expiry within seven days, content-free audit retention 90 days.
- 150 scenarios; 100 development/50 held-out; separate 30-output development and release human review samples.
- Only the user can approve reductions to accepted scope or release criteria.

## Review Focus

- Same-tenant users with document access must still be unable to read each other's conversations/checkpoints; Task 4.
- Revoked docs or private GitHub access must not survive via memory/checkpoint/restore; Tasks 4, 6, 11.
- A crash after dispatch can create uncertain execution; browser recovery/checkpoint resume must not repeat paid work silently; Task 4.
- Tenant/global reservation races and summary/discovery-triggered ingestion costs must not evade caps; Tasks 2, 4, 7, 10.
- Project/rescan/source revisions update future context while historical citations remain pinned; wrong-major or unapproved origins never enter retrieval; Tasks 4, 7, 8.

## File boundaries and execution conventions

The user authorized the scaffold, frontend preview, API skeleton, and database foundation, now mapped in [README.md](../README.md). All application paths and commands below are relative to the DocWeave repository root, even though this plan lives in `docs/`. Backend dependencies are uv-locked; frontend dependencies use npm. Add further dependencies only as their tasks need them. The existing runtime/schema are foundations, not completed authenticated product behavior; Git history and unrelated pending changes must be preserved.

| Location | Responsibility |
| --- | --- |
| `backend/src/docweave/main.py`, `settings.py`, `db.py` | App creation, configuration, runtime DB/session boundary |
| `auth.py`, `policy.py`, `projects.py` | OIDC sessions, tenant roles/grants, membership/invitations/project operations |
| `budget.py`, `providers.py` | Reservations/settlement and explicitly configured hosted profiles/adapters |
| `ingestion.py`, `sources.py`, `retrieval.py` | Durable lifecycle, approved source selection/fetch, version-scoped retrieval |
| `github.py`, `dependencies.py`, `documentation.py` | User-owned repo access/commit scans, static dependency facts, reviewed version-aware documentation discovery |
| `conversations.py`, `memory.py`, `workflow.py` | Author-private turns, protected checkpoints/summary, bounded graph |
| `telemetry.py`, `evaluation.py` | Content-safe operations and reproducible reports |
| `backend/alembic/`, `backend/tests/` | Migrations and unit/integration/security/failure checks |
| `frontend/src/app/`, `features/` | Application routing/bootstrap and feature-owned pages/state/components |
| `frontend/src/components/ui/`, `lib/`, `styles/` | Shared presentation controls, HTTP/browser helpers, global theme tokens |
| `frontend/tests/` | Playwright browser flows, including deterministic API fixtures |
| `backend/catalog/`, `backend/eval/` | Source manifests and versioned scenario/label/split/config data |
| `compose.yaml`, `.github/workflows/` | Reproducible local services and deterministic/manual-live CI |

Keep domain routes/schemas close to their owning modules. Split a module only when its responsibility grows; this map does not require a separate abstraction for every operation.

Backend checks run from repository root as `uv run --project backend pytest backend/tests/<file> -q`. Browser checks use `npm --prefix frontend exec -- playwright test`. Establish these commands during Task 1; they are future commands, not checks already run.

Task 1's pytest fixtures provide `owner_a`, `owner_b`, `member_a` authenticated ASGI clients, `workspace_a`, `project_a`, `project_b`, and `collection_a`, backed by a disposable PostgreSQL test database. Extend fixtures when each domain arrives. `drain_jobs(queue=...)` is a test-only deterministic queue runner. Fake OIDC/provider fixtures exist only in tests; production has no authentication-disable flag.

Each code task follows test -> observed failure -> minimal implementation -> relevant checks -> commit. Keep commits local; publishing/PRs/deployment are separate requests. Complete its learning check before marking the task done.

## Task 1 — Reproducible runtime and real access boundaries

**Files:** Create backend project/settings/db/main/auth/policy/projects modules, Alembic migrations, Compose, Keycloak realm-development configuration, test fixtures, `backend/tests/test_access.py`, and CI test bootstrap.

**Interfaces produced:** `Actor(user_id: UUID, workspace_id: UUID)`; `require_actor(request) -> Actor`; `authorize(actor: Actor, action: Literal["read","write","manage","infer"], resource_id: UUID) -> None`; `create_app() -> FastAPI`. Role/grant facts come from current DB state, never client Actor fields.

API documentation now exists as [openapi.yaml](../backend/openapi.yaml) and [api.md](api.md), a draft derived from the confirmed architecture. Reconcile its proposed wire details while implementing each owning task, compare FastAPI's generated contract, and test actual behavior. Structural documentation checks do not complete this or any later implementation task.

- [ ] Read public compatibility/model/source metadata and inspect Docker/reference hardware. Add and lock only this task's required dependencies with uv (backend) or npm (frontend); add later dependencies during their owning tasks. Record candidate versus verified status; do not claim account availability or make inference calls here.
- [ ] Write `test_cross_workspace_project_is_hidden`, `test_last_owner_cannot_be_removed`, and invitation/session/RLS tests. Minimum boundary assertion:

```python
async def test_cross_workspace_project_is_hidden(owner_a, project_b):
    response = await owner_a.get(f"/api/v1/projects/{project_b.id}")
    assert response.status_code == 404
```

- [ ] Run `uv run --project backend pytest backend/tests/test_access.py -q`; observe missing app/behavior failure before implementation.
- [ ] Implement migrations, runtime RLS/context roles, OIDC issuer/subject sessions, Google/GitHub/email methods, verification/reset, owner/maintainer/member policy, project context, and invitations. Expose health/readiness and stable safe errors.
- [ ] Use local SMTP capture for deterministic verification/reset. Document exact OAuth callbacks and configuration inputs; actual broker/account checks remain explicit release evidence, not something fake OIDC proves.
- [ ] Run access tests plus `docker compose config --quiet`; expect passing tenant/session/invitation/CSRF tests and valid Compose. Tests must exercise runtime-role connections, not only migration-owner access.
- [ ] Commit as `feat: establish authenticated workspace boundaries`.

**Learning/completion:** Explain identity versus membership/grants; trace one cross-tenant denial. Clean local setup supports verified email login, distinct tenants, project operations, invitation acceptance, and safe errors. Record which live social-provider checks are still pending.

## Task 2 — Workspace/global cost admission before hosted calls

**Files:** Create `budget.py`, initial `providers.py`, budget migrations/operator configuration, `backend/tests/test_budget.py`.

**Consumes:** Actor/policy/DB from Task 1.
**Produces:** `reserve_cost(actor: Actor, operation_key: str, profile_id: str, max_input_tokens: int, max_output_tokens: int) -> Reservation`; `settle_cost(reservation_id: UUID, actual_usd: Decimal | None, execution_uncertain: bool) -> None`. Reservation stores owner, workspace/month/profile, conservative USD amount, status, and operation key. Price calculations use Decimal, not float.

- [ ] Write `test_concurrent_reservations_respect_workspace_and_global_caps`: a workspace allowance of US$1 permits only one of two concurrent US$0.60 reservations; settlement/retry keys are idempotent.
- [ ] Add assertions that missing pricing rejects admission, uncertain execution retains its reservation, a new month uses Asia/Calcutta boundaries, and a tenant cannot read/raise another allowance.
- [ ] Run `uv run --project backend pytest backend/tests/test_budget.py -q`; verify failure before adding budget logic.
- [ ] Implement transactional reservation/reconciliation, operator-only workspace caps, own-tenant usage endpoints, initial profile capability/price records, and no-cap waiting behavior. New workspaces need an assigned allowance; global capacity is not a reserved tenant entitlement.
- [ ] Before enabling new adapters, replace the implemented Gemini-reranker requirement in generation eligibility with the actual Gemini-embedding/Groq-LLM pipeline requirements. Add a migration and role-specific consent/admission regressions; preserve immutable historical profiles and charges.
- [ ] Run tests and migration upgrade/downgrade on the disposable test DB; expect no double settlement, race overspend, float drift, or tenant financial disclosure.
- [ ] Commit as `feat: enforce tenant and global inference budgets`.

**Learning/completion:** Explain reservation versus final billing and uncertain usage. Fake-priced operations prove the boundary before any paid embedding, summary, or model call exists.

## Task 3 — Small-corpus ingestion, retrieval experiments and evaluation foundation

**Files:** Create ingestion/source/retrieval modules, restricted parser entrypoint/container, first FastAPI/PostgreSQL manifests, storage/index migrations and ingestion/retrieval tests. Start Task 10's evaluator, fixtures and reports here rather than creating a separate benchmark framework.

**Consumes:** Actor/policy, budget boundary, profile records.
**Produces:** `submit_document(actor: Actor, collection_id: UUID, upload: UploadFile) -> JobRef`; `import_source(actor: Actor, project_id: UUID, source_selection_id: UUID) -> JobRef`; `retrieve(actor: Actor, project_id: UUID, query: str, collection_ids: list[UUID], processor_ids: list[str], index_generation: str) -> list[Evidence]`. Evidence includes chunk/document/version IDs, exact quote/locator, source URL, and collection/provenance IDs.

### 3A — Durable ingestion

- [x] Write failing ingestion tests for a synthetic FastAPI-to-PostgreSQL connection/access runbook and frozen official fixtures: a dated rolling FastAPI snapshot and PostgreSQL 17 docs. Label FastAPI coverage honestly; do not claim exact package-version coverage.
- [x] Implement bounded TXT/Markdown parse/normalize/hash/chunk/stage/publish, transactional jobs/outbox, worker leases/recovery, private storage and source allowlist/redirect checks. Seed approved DocumentationSelection records; imports accept their IDs, not client-asserted trusted URLs. Fake embedding transports are confined to 3B's deterministic tests; hosted profiles wait for 3C.
- [x] Test same-content/config idempotency, failed replacement retaining the last good snapshot, immutable locators, post-wait authority and deletion during publication. Wrong-tenant or unapproved private text must never reach even a fake embedder.

### 3B — Scoped indexes and evaluation foundation

- [x] Add workspace/collection-owned chunk/embedding storage and RLS with transaction-local actor/workspace/generation context. Enforce current grants, approved technology/version entries, searchable snapshots, tombstones and compatible generations. A separate atomic searchable pointer preserves the previous good index through failed replacements; empty scope never broadens.
- [x] Implement native full-text and `sql-bm25-ident-v1` (k1=1.2, b=0.75) on PostgreSQL 17. Native ranking and true BM25 remain distinct; identifiers and authorized-only corpus statistics have independent regressions. The user chose SQL rather than a search extension.
- [x] Implement materialized filtered exact ranking and shared HNSW with RLS/metadata filters and bounded iterative scans. Real plans distinguish the paths; experiment settings, scan limits and underfill are recorded.
- [x] Start the evaluation CLI/report format with ten answerable development questions plus denial/no-evidence/version cases, frozen corpus hashes, exact source spans and scenario/family IDs. Labels remain pending human review; no held-out cases are used.
- [x] Build recorded-vector component reports and register four single-channel baselines plus four hybrid combinations. Record candidate ranks/plans/timing, shared index size, publication/build measurements, underfill, ANN Recall@30 and separate supporting Recall@10 denominators. Recordings bind to generation and exact question-file hashes. Semantic quality, hybrid fusion and reranking remain 3C.

### 3C — Hosted compatibility, bounded fusion and retrieval pilot

- [ ] Complete the document/provider gate in the [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md) before hosted corpus processing: deterministic scans, exact-version assessments, owner review, rescan jobs and indexing/retrieval/release fences. Existing 3A/3B completion evidence stays intact; these are unfinished follow-up checks.
- [ ] Implement the [structured prompt-writing rule](rules.md#structured-prompt-writing-rule) with shared versioned builders. Separate trusted task/rules/output contracts from JSON-encoded query/context/evidence for reranking and every later LLM role; test fake roles/delimiters as data. Semantic caching, general moderation and live guard models are excluded.
- [ ] Reconcile Task 2's processor requirements, then add Gemini embedding and Groq LLM-reranking adapters. Verify model-specific query/document configuration, dimensions, normalization, tokenizers, strict ranking schemas, returned-ID membership, billed reasoning/output limits and actual price/account compatibility.
- [ ] Run initial synthetic compatibility probes under reservations with a **US$0.25 total cap**. Pin eligible profiles only after evidence; missing credentials/prices/access keep hosted work waiting while fake-provider tests continue. Determine a working bounded Groq ranking output allowance rather than inheriting the old Gemini 512-token assumption.
- [ ] Implement up to 30 candidates/channel, deterministic deduplication and RRF `k=60`; rerank at most 20 bounded candidates with Groq, returning at most eight chunks/6,000 evidence tokens. Revalidate consent/access before external calls and evidence release; validate exact spans and source/version state.
- [ ] Embed the frozen corpus/queries through verified profiles, reuse compatible vectors within the authorized evaluation scope and execute all registered baselines/four hybrid configurations on identical inputs. Run the retrieval pilot without reranking and then with fixed Groq reranking. At least one pilot configuration must retrieve supporting passages in the final eight for 9/10 answerable questions; report failed variants explicitly and require isolation/version/no-evidence checks for every configuration. Do not select a production winner from ten questions alone.
- [ ] Run `uv run --project backend pytest backend/tests/test_ingestion.py backend/tests/test_retrieval.py backend/tests/test_evaluation_protocol.py -q`; record actual execution plans and results. Deliver 3A/3B/3C as separate reviewable checkpoints without claiming completion of unfinished stages.

**Learning/completion:** Explain hashes/version activation, RLS versus physical ANN filtering, exact versus approximate recall, native ranking versus BM25, RRF and LLM reranking. Task 4 adds backend answers and the end-to-end RAG pilot; frontend Task 5 is deferred.

## Task 4 — Persistent private conversations and durable graph turns

**Files:** Create `conversations.py`, `memory.py`, `workflow.py`, conversation/checkpoint/operation migrations, and `backend/tests/test_conversations.py` / `test_memory.py` / `test_turn_recovery.py`.

**Consumes:** Policy, profile/budget adapters, Evidence/retrieval and job primitives.
**Produces:** `create_conversation(actor: Actor, project_id: UUID, provider_profile_id: str, collection_ids: list[UUID]) -> ConversationRef`; `append_turn(actor: Actor, conversation_id: UUID, message: str, idempotency_key: str) -> TurnRef`; `read_turn(actor: Actor, turn_id: UUID) -> TurnView`; `run_turn(turn_id: UUID) -> None`. TurnView exposes execution state, optional result kind/text/citations, safe error, usage, and versions; authorization applies before reading it.

- [ ] Write an API test that repeated identical turn submissions return one turn ID and one dispatched fake operation:

```python
assert first.json()["turn_id"] == duplicate.json()["turn_id"]
assert fake_provider.operation_count("answer") == 1
```

- [ ] Add behavioral tests: same-tenant nonauthor denial; contextual follow-up; latest project revision on next turn; summary threshold with full transcript retained; clarification; invalid citation abstention; one active turn; no memory from another conversation.
- [ ] Add failure tests: crash after dispatch produces `completion_unknown`; resume does not call the provider again; revoked/deleted context blocks checkpoint/summary replay; normal refresh preserves old authorized citations. Test private approval before every helper/model call.
- [ ] Run the three test files and confirm meaningful failures before implementation.
- [ ] Implement the graph/context compiler and protected persistent checkpointer, provenance/dependency tracking, fixed-provider policy, 24,000/12,000-token allocation, bounded summaries and query resolution, and structured answer/clarification/abstention.
- [ ] Extend guardrails to chat and generated query/summary text. Block before hosted calls and exclude blocked content from model memory. Reuse structured prompts and provenance-aware preflight; approved evidence remains untrusted without being blanket-reblocked.
- [ ] Require documentation/project-context/inferred-advice blocks, validate source membership/spans/current access and render citations server-side before history/checkpoint writes. Invalid citations abstain, malformed output fails operationally, and credentials/access violations block release. Retain billing/uncertainty without automatic regeneration.
- [ ] Use verified Groq profiles for answers and required ambiguous-follow-up resolution; summarize with the conversation's fixed answer model. Extend Task 10's evaluator to execute actual backend turns and capture retrieved/reranked evidence, answers, citations, memory behavior and per-stage usage. Score correctness, faithfulness, relevance, citation support, abstention and privacy, not retrieval alone.
- [ ] Implement HTTP 202 durable turns, separate turn queue, per-conversation ordering/idempotency, operation dispatch ledger, polling/status recovery, current-access finalization, and uncertain-execution handling. No unvalidated token streaming or blind checkpoint replay.
- [ ] Run `uv run --project backend pytest backend/tests/test_conversations.py backend/tests/test_memory.py backend/tests/test_turn_recovery.py -q`; restart API/worker between accepted and completed fixture turns and expect the same recoverable result.
- [ ] Commit as `feat: persist contextual conversations with recoverable turns`.

**Learning/completion:** Explain stored transcript versus model context, summary provenance, checkpoint authorization, and paid-call uncertainty. Demonstrate a relevant follow-up and a revoked-source memory denial.

## Task 5 — Complete frontend vertical workflow and both themes

**Deferred:** The user currently authorizes backend work only. Retain this milestone for later integration; no UI implementation or browser gate blocks Tasks 3–4 or the backend RAG evaluator.

**Files:** Extend the existing frontend app/routes, shared theme/UI controls and feature-owned setup/chat/source/document/activity/settings flows; add vertical-flow/theme/conversation-recovery browser tests. Follow design.md's current simple-chat direction rather than its superseded workbench layout.

**Consumes:** API/resource/state contracts from Tasks 1–4 and design.md.
**Produces:** Keyboard-accessible complete small-corpus workflow; stable tenant/project/conversation/turn/citation navigation.

- [ ] Write Playwright checks: two isolated users; create project queues selected imports; upload a runbook; start a Groq conversation; answer a follow-up; open exact evidence; reload during a pending turn without a second POST.
- [ ] Add theme assertions: no override follows OS; toggle persists per device; both native controls and evidence dialog use the active theme; dark accent buttons use canvas-colored labels. Test storage failure, mobile sheet focus restoration, safe unavailable evidence, and no private content in URL/localStorage.
- [ ] Run `npm --prefix frontend exec -- playwright test`; observe missing app/flow failures.
- [ ] Integrate the existing simple chatbot: toggleable sidebar with New chat, workspaces/nested chats and recent chats; source drawer on citation selection; fixed model under Chat options; sign-in/invitations, processing approvals, own-workspace allowance, import states, clarification, condensed-context disclosure and durable recovery.
- [ ] Preserve current responsive sidebar/source-drawer behavior, empty-chat state, keyboard focus and draft protection. The old permanent project rail/adjacent evidence inspector is superseded by design.md's current direction.
- [ ] Run Playwright plus the frontend production build. Expect all flow/state tests passing, keyboard usability, no cross-tenant flashes, and a usable 320px/200%-zoom layout.
- [ ] Commit as `feat: deliver the conversational evidence workbench`.

**Learning/completion:** Walk the small-corpus integration problem end to end and explain one async/privacy/UI failure. This completes the first vertical milestone, not the full release.

## Task 6 — User-owned GitHub connection and static stack review

**Files:** Create `github.py`, `dependencies.py`, connection/scan/dependency/StackReview migrations, `backend/tests/test_github_access.py`, `test_dependency_scan.py`; frontend account connections, repository/branch/application picker, stack preview; `frontend/tests/github-setup.spec.ts`.

**Consumes:** Actor/policy/session, durable ingestion job infrastructure and project/context revision. Backend scan APIs do not depend on deferred frontend integration; browser steps resume only with frontend work.
**Produces:** `request_repository_scan(actor: Actor, repository_id: int, branch: str, application_path: str) -> ScanRef`; `read_repository_scan(actor: Actor, scan_id: UUID) -> ScanView`; `parse_dependencies(files: dict[str, bytes], application_path: str) -> DependencyScan`; `confirm_stack(actor: Actor, scan_id: UUID, selections: list[StackSelection]) -> StackReviewRef`. DependencyScan contains facts, safe warnings, and completeness. Facts separate package/ecosystem/role/directness/path/field, declaration, resolution/revision, conditions, status. StackSelection records selected dependency and optional user-chosen docs target without overwriting detected facts.

- [ ] Write authorization tests using fake GitHub transport: user/app intersection, organization approval, expired/revoked tokens, private derived project-list/scan denial, cross-tenant review IDs, current-viewer access, background authority recheck, and no shared installation-token bypass. Example:

```python
response = await member_a.get(f"/api/v1/repository-scans/{private_scan.id}")
assert response.status_code == 404
assert fake_github.fetched_paths == []
```

- [ ] Write parser fixtures for requirements/includes/constraints/markers/extras, standard pyproject/dynamic fields, uv.lock, package.json aliases/workspaces, package-lock, and pnpm importers. Assert declarations differ from resolutions/overrides, frozen-list role/directness stays unknown without evidence, constraint-only entries are never auto-selected, and conditional/unsupported data remains explicit.
- [ ] Add include cycles/escapes/external URLs, unsafe YAML, credentials in URLs, malformed/unsupported lock schemas, mismatched manifests, monorepo version separation, partial tree/file caps, symlinks/submodules/LFS, and commit-changing-during-scan cases. Every fetched file uses the resolved SHA; raw bytes/private values never enter persistent facts/logs/model calls.
- [ ] Run `uv run --project backend pytest backend/tests/test_github_access.py backend/tests/test_dependency_scan.py -q`; observe missing behavior failures before implementation.
- [ ] Implement GitHub App connection separate from Keycloak sign-in, encrypted user credentials, selected-repo policy, bounded immutable snapshot fetch, normalized dependency facts, and private scan/review ownership. No repo cloning, package installation, code/config execution, or private-index authentication.
- [ ] Build the optional setup preview: branch defaults, selected application, provenance/uncertainty, runtime preselection, optional dev tools, manual fallback, and unresolved docs-version choices. Preserve unsupported ecosystems/lockfiles visibly.
- [ ] Run backend tests plus `npm --prefix frontend exec -- playwright test tests/github-setup.spec.ts`; expect safe accessible preview, no private-name leaks, and no imports before stack confirmation.
- [ ] Later, with implementation authorization and configured GitHub App, verify public/private/organization access and disconnect behavior against a controlled repository; do not count mocked transport as live account verification.
- [ ] Commit as `feat: detect reviewed project stacks through read-only GitHub access`.

**Learning/completion:** Explain login versus repository authorization, GitHub permission versus application file policy, coherent commit snapshots, declared versus resolved versus deployed versions, and one malicious/partial scan case. The scan/review is complete; documentation discovery/import integration belongs to Task 7.

## Task 7 — Version-aware docs discovery, approval, and reviewed rescans

**Files:** Create `documentation.py`, DocumentationSelection/SourceApproval/lookup-consent migrations; extend sources/projects/retrieval and GitHub binding/apply operations; `backend/tests/test_documentation_discovery.py`, `test_version_selection.py`, `test_rescan_policy.py`; frontend new-source/version/diff review; `frontend/tests/documentation-review.spec.ts`.

**Consumes:** Task 6 scan/fact/review IDs, Task 3 `import_source(..., source_selection_id)`, current processing policy, budget/fetch guards, and conversation revision/dependency tracking.
**Produces:** `discover_documentation(actor: Actor, project_id: UUID, dependency_ids: list[UUID], lookup_consent_revision: int | None) -> list[DocumentationCandidate]`; `approve_documentation(actor: Actor, project_id: UUID, candidate_ids: list[UUID], accepted_fallback_ids: list[UUID]) -> list[DocumentationSelectionRef]`; `apply_repository_review(actor: Actor, project_id: UUID, review_id: UUID) -> ProjectView`. Candidates are immutable server-stored package/origin/path/version/provenance proposals, not client assertions of trusted URLs.

- [ ] Write catalog-first tests: version-supported routes auto-select; unknown origins do not import before review; user approval stays project/workspace-scoped; registry metadata is labeled publisher-linked, not independently verified.
- [ ] Assert absent lock resolution requires target selection, major/minor fallback requires acceptance, exact-unavailable cannot silently select latest, and retrieval cannot mix incompatible version scopes. Declaration/resolution/selected target/actual docs coverage remain separate.
- [ ] Assert private/local/Git/URL/unresolved identifiers trigger no public lookup without consent; lookups send normalized identifiers only, never raw files/private URLs. Approved immutable external origin/path scopes can fetch without global catalog promotion; other scopes/private-address redirects/download content remain blocked. Assert GitHub credentials never reach documentation/registry clients.
- [ ] Write rescan tests: branch movement alone does not mutate context; applying a reviewed commit diff updates the next turn; historical authorized citations retain old snapshots; lost upstream access blocks old facts/summaries and background apply/import; manual projects still work.
- [ ] Run `uv run --project backend pytest backend/tests/test_documentation_discovery.py backend/tests/test_version_selection.py backend/tests/test_rescan_policy.py -q`; verify meaningful preimplementation failures.
- [ ] Implement deterministic catalog -> approved package/release registry metadata -> publisher-linked candidate resolution, explicit scope/version consent, reviewed official URL/upload fallback, and unavailable/partial states. Discovery itself never gives the answer graph autonomous browsing tools.
- [ ] Connect setup: confirmed stack plus user goal creates the project and queues approved catalog selections; project-scoped unknown-source review follows in setup/Sources. Approved new selections reuse Task 3 ingestion; no nonexistent-project dependency or unreviewed-origin autoimport.
- [ ] Implement manual diff/apply and upstream-aware private context/provenance views. Scan IDs/reviews cannot be reused across actors/tenants; source approval/processing grants and budget guards are rechecked at dispatch/publication.
- [ ] Run backend tests and `npm --prefix frontend exec -- playwright test tests/documentation-review.spec.ts`; expect known imports, pending unknown/version states, isolated approvals, rejected malicious sources, and recoverable reviewed diffs.
- [ ] Validate representative noncatalog/versioned sources with bounded live public metadata/import checks after implementation authorization. Retain clear publisher/coverage limitations; never claim docs exist for every detected package.
- [ ] Commit as `feat: import reviewed version-matched documentation beyond the catalog`.

**Learning/completion:** Explain publisher evidence versus source verification, explicit version fallback, private identifier egress, and why a rescan needs approval. Full release source coverage still requires Task 8.

## Task 8 — Full document lifecycle and all 29 sources

**Files:** Extend ingestion/sources/parser and lifecycle migrations, remaining `backend/catalog/*.yaml`, `backend/tests/test_document_lifecycle.py`, `test_source_registry.py`, and `backend/eval/catalog-smoke.jsonl`; extend frontend source/document/activity pages.

**Consumes:** Working index/retrieval/answer/citation path, Tasks 6–7's scan/version/approval contracts, and worker/policy contracts.
**Produces:** Full PDF/TXT/Markdown/DOCX support, bounded verified catalog coverage, refresh/version/re-index/deletion/recovery behavior.

- [ ] Write parameterized format/manifest tests plus one evidence-linked development smoke scenario per entry. Earlier tasks now provide the answer/citation path these checks consume.
- [ ] Add malformed/encrypted/scanned/oversized/archive-bomb files, scanner outage/disabled state, parser timeout/memory limit, worker crash/lease recovery, malicious redirects/DNS targets, partial import, removed page, unchanged hash, and re-index/config-dimension tests.
- [ ] Run `uv run --project backend pytest backend/tests/test_document_lifecycle.py backend/tests/test_source_registry.py -q`; observe unsupported-format/manifest/lifecycle failures.
- [ ] Implement remaining parsers/manifests, exact seeds/path/attribution/robots/version-routing notes, source/project caps across catalog and approved external sources, actual publisher-version coverage, retries/checkpoints, and atomic replacement.
- [ ] Verify all 29 using bounded live imports and representative final answer/citation smoke scenarios under reservations. Public fixtures prove regressions; live results establish current support. Unverified entries remain planned/imported.
- [ ] Run lifecycle/source tests and the 29-entry smoke suite; expect all entries verified or an explicit unresolved release blocker. No silent catalog reduction.
- [ ] Commit as `feat: verify catalog coverage and document lifecycle`.

**Learning/completion:** Explain source provenance/coverage versus whole-site claims; demonstrate failed refresh retaining a good snapshot and deletion resisting retry resurrection.

## Task 9 — Groq hosted-role profiles and adapter hardening

**Files:** Extend providers/profile configuration, `backend/tests/test_provider_contracts.py` and evaluation configuration manifests. Frontend profile integration remains deferred.

**Consumes:** Task 3's Gemini embedding/Groq reranking adapters and Task 4's Groq conversation/helper roles, budget and dispatch contracts.
**Produces:** Verified pinned Groq LLM-role profiles and Gemini embedding profiles; fixed conversation model selection and no automatic routing.

- [ ] Write parameterized adapter contracts for schema/ID validation, total billed reasoning/output accounting, timeouts, tokenizers, role-specific processor consent, fixed conversation models and missing-price refusal.
- [ ] Run `uv run --project backend pytest backend/tests/test_provider_contracts.py -q`; verify the new hardening cases fail before changing the existing adapters.
- [ ] Harden the existing adapters across answer, rerank, query-resolution, summary and offline-judge roles, including strict output bounds, refusals, retries and uncertain execution. Preserve historical profiles/charges; do not add Gemini/HF answer adapters or the future LLM gateway.
- [ ] Restrict newly enabled LLM profiles/dispatch to Groq and embedding profiles/dispatch to Gemini. Historical identities remain readable for usage/history; provider enums alone do not authorize a new call outside the selected pipeline.
- [ ] Reuse the initial compatibility evidence and reserve any further required exact-model/account checks. Record schema support, billed reasoning/output bounds, request configuration, tokenizer windows, rates and latency; unsupported candidates stay unavailable.
- [ ] Run adapter tests and authorized follow-up/citation/revocation cases through the selected Groq profiles, including independently accounted helper/judge calls and Gemini embedding consent.
- [ ] Commit as `feat: verify Groq hosted-role contracts`.

**Learning/completion:** Explain model publisher versus serving provider, role-specific consent/billing, adapter guarantees and why comparisons freeze generation/history settings.

## Task 10 — End-to-end RAG evaluation pipeline and held-out quality gates

**Files:** Extend `evaluation.py` and evaluation-protocol tests; add scenario/label/split/family/config manifests and reports as the complete RAG workflow arrives.

**Consumes:** Start with Task 3's corpus/retrieval fixtures, add Task 4's complete backend RAG turns, then expand to all catalog sources and architecture's 150-scenario allocation. This is ongoing evaluation work, not a final-stage-only retrieval benchmark.
**Produces:** CLI `python -m docweave.evaluation --split development|held-out --config <path>` driving actual authorized backend RAG services; per-case and aggregate JSON/CSV reports with corpus/profile/config/prompt/hash/date/cost provenance and captured evidence, answers and citations.

- [ ] Start the versioned scenario/config/report schema in Task 3 and connect complete RAG execution in Task 4. Each case records question/ordered history, actor/project/source/version scope, expected supporting passages/required facts, expected answer/clarification/abstention behavior and prohibited disclosures. Use synthetic private fixtures and protect captured evaluation content from ordinary logs/cross-tenant access.
- [ ] Write staged protocol tests: the initial 10-question development pilot, then the complete 150 scenarios/100 development/50 held-out split, no family overlap, 29 development coverage checks and separate human-rating samples. Held-out cases never select retrieval defaults, models, prompts or judges.
- [ ] Add deterministic metric tests for labeled context precision/recall, Recall/MRR/nDCG where labels support them, ANN Recall@k versus exact search, underfill and structural citation/span checks. Add semantic answer correctness/required-fact coverage, faithfulness to supplied evidence, response relevance and citation-to-claim support; faithfulness is not a substitute for correctness.
- [ ] Evaluate abstention/clarification, follow-ups, summary continuity, version/staleness/conflicts, adversarial documents, source/upstream revocation and tenant/conversation isolation. Security failures disqualify a configuration rather than being averaged into its quality score. Record scenario and turn counts separately.
- [ ] Add guardrail regressions for structured sections/fake roles, injection flags/benign examples, credentials, owner-review races, changed rules/hashes, safe older indexes, quarantine/deletion/revocation and rejected-output persistence. Assert forbidden inputs never reach fake providers; report false positives/outcomes/overhead without claiming complete detection. Keep the 150-scenario split/human-review protocol; add deterministic boundary cases separately.
- [ ] Run `uv run --project backend pytest backend/tests/test_evaluation_protocol.py -q`; observe missing evaluator/protocol failures.
- [ ] Implement the CLI/report runner incrementally and human-verify reference labels. Compare native full-text/BM25 crossed with exact/HNSW vectors plus lexical-only/vector-only baselines, first at retrieval and then through complete generation with the same Groq answer profile, prompts/history, reranker settings, evidence budgets and query embeddings. Choose defaults using broader development end-to-end quality, latency/cost and operational complexity; prefer the simpler path when results are effectively tied.
- [ ] Assess Ragas for semantic metrics without committing to it before Groq compatibility/cost validation. Configure all hosted judge LLM calls explicitly through Groq, with Gemini used only for any required embeddings; no framework-default provider calls. Capture per-stage/end-to-end p50/p95, token/cost totals, query plans, HNSW settings, index build time/size, machine identity, failures and configuration differences.
- [ ] Human-review 30 development outputs to calibrate any automated judge; freeze rubric/prompts/profiles/targets. Budget the actual turn/summary/reranking/judging workload, not just 150 generation calls.
- [ ] Run deterministic metric/regression tests; then the separately budget-reserved held-out run and distinct 30-output human release review. Publish denominators, failures, costs, and source/model versions.
- [ ] Commit as `test: establish reproducible end-to-end RAG evaluation`.

**Learning/completion:** Explain development versus held-out evidence, summary-memory evaluation, judge disagreement, and one actual failure. Missing thresholds remain failures; only the user can approve a reduced bar.

## Task 11 — Operations, deletion, restore, and failure/load drills

**Files:** Create telemetry module/profile/dashboards/alert configuration; backup/restore and deletion-runbook documentation; `backend/tests/test_restore.py`, `test_deletion.py`, `test_telemetry_privacy.py`; deterministic/manual-live CI workflows.

**Consumes:** Persisted application/index/checkpoint/usage state.
**Produces:** Safe observability, tested recovery, enforced retention, reproducible load/failure results.

- [ ] Write tests that deletion denies access immediately, purges live content/checkpoints/writes within the running-service deadline, expires seven-day backups, and retains only 90-day content-free audit records.
- [ ] Create a pre-deletion backup fixture; delete/revoke, restore the old backup, apply the deletion journal/current policy before readiness, and assert neither inference nor evidence/history can expose the old content.
- [ ] Add assertions that source text, raw configs, private repo labels/URLs, messages/summaries/answers, tokens/cookies/secrets are absent from logs/traces; tenant usage remains isolated. Restore GitHub-derived state blocked until upstream checks succeed, while manual projects remain usable.
- [ ] Run the three test files and observe missing operations/privacy behavior.
- [ ] Implement scheduled cleanup, startup overdue-deletion reconciliation, backup/restore/migration recovery, safe metrics/traces/dashboards/alerts, rate/queue limits, and explicit uncertain-operation runbooks.
- [ ] Run tests, a clean restore drill, worker/provider failure drills, and one/five-turn load runs on recorded hardware/corpus. Report actual p95 and bottlenecks against targets; live provider timing is not inferred from fake tests.
- [ ] Commit as `feat: verify operational recovery and retention`.

**Learning/completion:** Demonstrate one restart/restore/deletion failure path and explain why a DB restore alone cannot resurrect permissions or deleted memory.

## Task 12 — Full portfolio release evidence

**Files:** Complete repository README, API/setup/demo/threat-model/runbook/architecture-decision documentation and learning evidence; update these planning files/memory with actual results.

- [ ] Reproduce the synthetic integration scenario from a clean checkout, including all logins, two tenants, manual and GitHub setup, private uploads, reviewed/version-aware imports, unknown-source fallback, remembered clarification/follow-up, citations, rescan/revocation/delete/recovery, and both themes.
- [ ] Confirm all 29 catalog entries, selected Groq LLM/Gemini embedding profiles, the end-to-end RAG benchmark/human review, CI, security boundaries, budget gates, retention and recovery evidence have passed. Mark account/model/source limitations honestly; the future LLM gateway is not a release gate.
- [ ] Have a fresh reviewer assess implementation correctness, isolation/memory privacy, evaluation claims, and original-brief coverage; resolve actionable findings and rerun affected checks.
- [ ] Record the short demonstration and milestone learning explanations; verify another engineer can reproduce setup from the independent repository without private fixtures/secrets.
- [ ] Commit as `docs: publish reproducible DocWeave portfolio evidence`.

**Completion:** Every PRD release outcome has evidence, the builder can explain and diagnose the system, and accepted scope/criteria were not weakened without the user's agreement. Hosting/customer deployment remain separate requests.

## Plan self-review and execution boundary

Public candidate selection does not claim account verification; budget/consent admission precedes live probes. Evaluation begins with retrieval in Task 3, exercises full backend RAG in Task 4 and expands to the frozen release benchmark in Task 10. Native/BM25 and exact/HNSW choices stay experimental until development evidence selects defaults. Backend Tasks 6–7 consume the manual backend workflow; all frontend steps remain deferred. The 29-source, memory/privacy, budget, recovery and unchanged held-out quality gates remain required, with Groq as the sole current LLM service and Gemini as the embedding-only exception.

All checkboxes above remain unchecked. This is a plan, not executed code or proof of passing tests. When the user later requests implementation, select the execution method then and use the corresponding Superpowers execution workflow. Do not start implementation merely because the written design is confirmed.
