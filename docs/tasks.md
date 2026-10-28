# DocWeave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build the confirmed multi-tenant, evidence-grounded, conversational DocWeave release.
**Architecture:** One modular FastAPI backend, PostgreSQL/pgvector, durable ingestion/turn/scan jobs, protected LangGraph memory, and a React frontend. Deliver the manual small-corpus vertical workflow first; then add optional GitHub stack detection, version-aware source discovery, the full catalog/providers, evaluation, and operations.
**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/Alembic, PostgreSQL/pgvector/Procrastinate, LangGraph/LangChain, Keycloak, React/TypeScript/Vite, Docker Compose, pytest, Playwright, OpenTelemetry.
**Spec:** [PRD.md](PRD.md), [architecture.md](architecture.md), and frontend [design.md](design.md).
**Status:** Plan and GitHub extension reconciled on 2026-10-28. The frontend preview, tested API skeleton, and PostgreSQL/core-schema foundation are implemented as separately authorized slices. Complete authenticated product workflows remain unimplemented. No full-release task below is complete solely because its infrastructure exists.

On 2026-10-29, backend contract tests were added in `backend/tests/test_openapi.py`, with uv-locked dev dependencies. All 70 tests passed; 12 in-memory contract mutations were detected. This validates the draft contract only; the runtime/security/integration tests and task checkboxes below remain unfinished.

Frontend progress on 2026-10-29: a labeled synthetic Ask workbench now implements citation/evidence interaction, responsive shadcn sheets, Tailwind themes, provider selection, and draft/history protection. Build, lint, and 11 browser checks pass, including automated accessibility scans. This preview has no live backend integration and does not complete any full-release task below. See [workbench slice](superpowers/plans/2026-10-29-workbench.md) for scope and evidence.

The user then clarified that backend work must follow TDD and authorized every draft operation as an HTTP skeleton, with business logic, database and AI deferred. Tests were written and run first (75 runtime failures from the missing app; 70 contract checks passing), then the minimal FastAPI app was added. All 145 checks now pass with warnings treated as errors. Liveness returns 200, readiness 503, and the other 67 operations 501; runtime docs describe those actual responses. A temporary local Uvicorn check passed and was stopped. See the [skeleton plan](superpowers/plans/2026-10-29-api-skeleton.md). Authentication, request-body validation, persistence, and full Task 1 acceptance remain unimplemented; no full-release milestone is complete.

Database progress on 2026-10-29: implemented the user-approved [database foundation](superpowers/plans/2026-10-29-database-foundation.md): pinned PostgreSQL/pgvector Compose services, explicit Alembic migration, core models, SELECT-only runtime role, membership-backed RLS, and transaction-local sessions. Development is migrated at `0001_core` and survived restart; 51 database checks plus the existing 145 checks passed (196 total, warnings as errors). The disposable test service is separate from development and its target guard rejects query overrides. Authentication, application writes, full business authorization, and overall readiness remain deferred. See the [database runbook](runbooks/database.md). Task 1 remains incomplete.

## Future goal outside this release

After the core application workflow works and is evaluated, introduce an MCP server for authorized knowledge search and cited evidence retrieval, reusing the web application's backend retrieval and policy checks. See [Future goals](PRD.md#future-goals). This is not an active implementation task or a dependency of the current release; tool contracts, client authentication, and compatibility checks will be planned when scheduled.

## Global Constraints

- Workspace is the tenant; conversations are author-private and project-bound.
- Google, GitHub, verified email/password; owner-issued recipient-bound invitations.
- Gemini embeddings and bounded Gemini LLM reranking; Gemini/Groq/HF hosted answer providers.
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
- [ ] Run tests and migration upgrade/downgrade on the disposable test DB; expect no double settlement, race overspend, float drift, or tenant financial disclosure.
- [ ] Commit as `feat: enforce tenant and global inference budgets`.

**Learning/completion:** Explain reservation versus final billing and uncertain usage. Fake-priced operations prove the boundary before any paid embedding, summary, or model call exists.

## Task 3 — Small-corpus ingestion and scoped retrieval

**Files:** Create `ingestion.py`, `sources.py`, `retrieval.py`, restricted parser entrypoint/container, first FastAPI/PostgreSQL manifests in `backend/catalog/`, storage/index migrations, and `backend/tests/test_ingestion.py` / `test_retrieval.py`.

**Consumes:** Actor/policy, budget boundary, profile records.
**Produces:** `submit_document(actor: Actor, collection_id: UUID, upload: UploadFile) -> JobRef`; `import_source(actor: Actor, project_id: UUID, source_selection_id: UUID) -> JobRef`; `retrieve(actor: Actor, project_id: UUID, query: str, collection_ids: list[UUID], processor_ids: list[str], index_generation: str) -> list[Evidence]`. Evidence includes chunk/document/version IDs, exact quote/locator, source URL, and collection/provenance IDs.

- [ ] Write ingestion tests for a synthetic TXT runbook and small frozen official-doc fixtures. Assert ready jobs have immutable locators, duplicate content does not add a version, wrong-tenant/private-unapproved text never reaches a fake embedder, and deletion during publication cannot reactivate a document.
- [ ] Write retrieval tests for lexical/vector candidates, RRF `k=60`, grants/tombstones/active generation, deterministic duplicate handling, and recorded source spans.
- [ ] Run both test files; observe missing pipeline/retrieval failures.
- [ ] Implement the shared bounded parse/normalize/hash/chunk/embed/stage/publish path, job/outbox transaction, safe worker leases, budget-aware batches, and source allowlist/redirect checks. Seed DocumentationSelection records from the two catalog fixtures with explicit package/docs target/coverage; imports consume these approved selection IDs. Begin with TXT/Markdown; full catalog support is not yet claimed.
- [ ] Add Gemini embedding/LLM-reranking adapters. After implementation authorization and Task 2's admission boundary, run tiny synthetic budget-reserved compatibility probes: dimensions, normalization, tokenizer/input limits, structured ranking output, billing identity, and prices. Missing keys/access do not block fake tests, but cannot pass this live gate.
- [ ] Implement full-text/vector fusion, at most 20 bounded rerank candidates, and final eight-chunk/6,000-token evidence budget. Freeze IDs/configuration; no silent token truncation.
- [ ] Run `uv run --project backend pytest backend/tests/test_ingestion.py backend/tests/test_retrieval.py -q`; expect passing pipeline/isolation/ranking tests.
- [ ] Commit as `feat: ingest a bounded corpus and retrieve authorized evidence`.

**Learning/completion:** Explain hashes/version activation, lexical versus vector retrieval, RRF, and LLM reranking. The small corpus is indexable/retrievable; end-to-end answer support is not claimed until Tasks 4–5.

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
- [ ] Implement HTTP 202 durable turns, separate turn queue, per-conversation ordering/idempotency, operation dispatch ledger, polling/status recovery, current-access finalization, and uncertain-execution handling. No unvalidated token streaming or blind checkpoint replay.
- [ ] Run `uv run --project backend pytest backend/tests/test_conversations.py backend/tests/test_memory.py backend/tests/test_turn_recovery.py -q`; restart API/worker between accepted and completed fixture turns and expect the same recoverable result.
- [ ] Commit as `feat: persist contextual conversations with recoverable turns`.

**Learning/completion:** Explain stored transcript versus model context, summary provenance, checkpoint authorization, and paid-call uncertainty. Demonstrate a relevant follow-up and a revoked-source memory denial.

## Task 5 — Complete frontend vertical workflow and both themes

**Files:** Create frontend package/routes, `src/app.tsx`, `src/app/` routing/bootstrap, `src/styles/theme.css`, feature-owned project/Ask/source/document/activity/settings pages and shared UI controls; `frontend/tests/vertical-flow.spec.ts`, `theme.spec.ts`, `conversation-recovery.spec.ts`.

**Consumes:** API/resource/state contracts from Tasks 1–4 and design.md.
**Produces:** Keyboard-accessible complete small-corpus workflow; stable tenant/project/conversation/turn/citation navigation.

- [ ] Write Playwright checks: two isolated users; create project queues selected imports; upload a runbook; start Gemini conversation; answer a follow-up; open exact evidence; reload during a pending turn without a second POST.
- [ ] Add theme assertions: no override follows OS; toggle persists per device; both native controls and evidence dialog use the active theme; dark accent buttons use canvas-colored labels. Test storage failure, mobile sheet focus restoration, safe unavailable evidence, and no private content in URL/localStorage.
- [ ] Run `npm --prefix frontend exec -- playwright test`; observe missing app/flow failures.
- [ ] Implement the evidence-first workbench, recent-conversation picker within Ask, fixed provider badge, complete sign-in/invitation states, processing approvals, own-workspace allowance, automatic import states, clarification, condensed-context disclosure, and durable turn recovery.
- [ ] Preserve the existing layout arithmetic: 224px rail, 480px discussion, 360px inspector fit at desktop; compact evidence becomes modal below 1,200px. Do not add an always-visible extra history rail.
- [ ] Run Playwright plus the frontend production build. Expect all flow/state tests passing, keyboard usability, no cross-tenant flashes, and a usable 320px/200%-zoom layout.
- [ ] Commit as `feat: deliver the conversational evidence workbench`.

**Learning/completion:** Walk the small-corpus integration problem end to end and explain one async/privacy/UI failure. This completes the first vertical milestone, not the full release.

## Task 6 — User-owned GitHub connection and static stack review

**Files:** Create `github.py`, `dependencies.py`, connection/scan/dependency/StackReview migrations, `backend/tests/test_github_access.py`, `test_dependency_scan.py`; frontend account connections, repository/branch/application picker, stack preview; `frontend/tests/github-setup.spec.ts`.

**Consumes:** Actor/policy/session, durable ingestion job infrastructure, project/context revision and existing frontend.
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

## Task 9 — Groq and Hugging Face answer profiles

**Files:** Extend providers/profile configuration, `backend/tests/test_provider_contracts.py`, `backend/eval/provider-compare.yaml`, frontend new-conversation profile selection.

**Consumes:** Existing Gemini retrieval, budget, memory/answer contracts.
**Produces:** Explicit compatible Gemini/Groq/HF generation profiles with immutable conversation selection.

- [ ] Write parameterized adapter contracts for schema output, total billed output accounting, timeouts, tokenizers, fixed provider, missing-price refusal, and no silent HF backend routing/fallback.
- [ ] Run `uv run --project backend pytest backend/tests/test_provider_contracts.py -q`; verify absent adapters fail.
- [ ] Implement Groq and HF hosted generation only; do not reintroduce local HF inference or HF cross-encoder retrieval. Keep summaries on the conversation's approved provider, while Gemini retrieval approvals remain required.
- [ ] Run tiny synthetic reserved account probes for each exact model/backend. Record available structured-output behavior, billed reasoning/output bounds, request schemas, tokenizer windows, current rates, and latency; lock supported profiles. Unsupported candidates are not counted as verified.
- [ ] Run adapter tests and a shared authorized follow-up/citation scenario through all three providers; expect compatible final responses and clear failures without changing provider.
- [ ] Commit as `feat: verify three hosted answer providers`.

**Learning/completion:** Explain model publisher versus serving provider, adapter versus model guarantees, and why comparisons freeze retrieval/history.

## Task 10 — Versioned benchmark and uncontaminated quality gates

**Files:** Create `evaluation.py`, `backend/eval/scenarios.jsonl`, labels/split/family/config manifests and reports, `backend/tests/test_evaluation_protocol.py`.

**Consumes:** All catalog/profiles and architecture's 150-scenario allocation.
**Produces:** CLI `python -m docweave.evaluation --split development|held-out --config <path>`; machine-readable reports with corpus/profile/config/hash/date/cost provenance.

- [ ] Write protocol tests: 150 scenarios, 100/50 split, no family overlap, 29 development coverage checks, separate human-rating samples, and no provider-selection/calibration use of held-out cases.
- [ ] Add metric assertions for known Recall/MRR/nDCG labels, unanswerable/clarification cases, follow-up decisions, source/upstream revocation, summary leakage, and representative GitHub-derived/version-mismatch scenarios within the existing 150 allocation. Multi-turn scenarios expose both scenario and turn counts.
- [ ] Run `uv run --project backend pytest backend/tests/test_evaluation_protocol.py -q`; observe missing evaluator/protocol failures.
- [ ] Implement the report/CLI; create and human-verify the labeled corpus. Compare four retrieval configurations, then three answer providers on 30 development scenarios with identical authorized context.
- [ ] Human-review 30 development outputs to calibrate any automated judge; freeze rubric/prompts/profiles/targets. Budget the actual turn/summary/reranking/judging workload, not just 150 generation calls.
- [ ] Run deterministic metric/regression tests; then the separately budget-reserved held-out run and distinct 30-output human release review. Publish denominators, failures, costs, and source/model versions.
- [ ] Commit as `test: establish reproducible conversation and retrieval evaluation`.

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
- [ ] Confirm all 29 catalog entries, all three answer providers, human review, CI, security boundaries, budget gates, retention, and recovery evidence have passed. Mark account/model/source limitations honestly.
- [ ] Have a fresh reviewer assess implementation correctness, isolation/memory privacy, evaluation claims, and original-brief coverage; resolve actionable findings and rerun affected checks.
- [ ] Record the short demonstration and milestone learning explanations; verify another engineer can reproduce setup from the independent repository without private fixtures/secrets.
- [ ] Commit as `docs: publish reproducible DocWeave portfolio evidence`.

**Completion:** Every PRD release outcome has evidence, the builder can explain and diagnose the system, and accepted scope/criteria were not weakened without the user's agreement. Hosting/customer deployment remain separate requests.

## Plan self-review and execution boundary

This sequence repairs the old circular gates: public candidate selection does not claim account verification; the budget boundary precedes live probes; final source-answer checks follow a working answer/citation path. Conversational memory/summary, async recovery, three login methods, optional GitHub scans, reviewed version-aware discovery, dark mode, own-tenant cost visibility, and restore-safe deletion are explicitly assigned. Tasks 6–7 consume the working manual path and share its approval/import contract; the 29-entry completion gate follows them.

All checkboxes above remain unchecked. This is a plan, not executed code or proof of passing tests. When the user later requests implementation, select the execution method then and use the corresponding Superpowers execution workflow. Do not start implementation merely because the written design is confirmed.
