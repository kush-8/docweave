# DocWeave — Session Memory

Updated: 2026-10-29 (Asia/Calcutta). Phase: folder scaffold, backend manifest, frontend starter, and draft OpenAPI documentation present; product features unstarted.

## Read first

The six planning files live in `docweave/docs/`: [PRD.md](PRD.md), [architecture.md](architecture.md), [design.md](design.md), [rules.md](rules.md), [tasks.md](tasks.md), and this file. [README.md](../README.md) now maps the initialized folders. PRD owns intent, architecture owns system behavior, design is specifically frontend/app flow, rules owns engineering constraints, tasks owns execution state. This summary does not override them.

API documentation is [openapi.yaml](../backend/openapi.yaml) with [api.md](api.md). It is a draft design contract; no backend routes exist. Architecture still owns behavior. The guide labels proposed wire details and the boundary between structural validation and runtime proof. At the user's request, the specification lives in `backend/`; its usage guide remains in `docs/`.

## Confirmation and authorization

After multi-round grilling, the user confirmed the original scope and GitHub extension. They subsequently authorized the folder structure, a backend pyproject.toml, and React/Vite frontend initialization. The frontend's required starter dependencies are included; product features, backend dependency installation, Git initialization, credentials, and paid inference remain future work. No further design-approval loop is needed for the confirmed direction.

The user is building an advanced AI engineering portfolio to learn and showcase AI application delivery / forward deployed engineering. Full scope is retained; delivery begins with a complete small-corpus vertical workflow and expands afterward.

## Confirmed decisions

- DocWeave; local Docker-based application with real multi-tenant authentication/authorization, not demo-only tenant identities.
- Workspace is tenant; independent memberships across workspaces; owner/maintainer/member roles plus collection grants.
- Google/GitHub OAuth and verified email/password; reset/verification; owner-issued expiring, single-use, recipient-bound invitations.
- Project goal and stack required; optional architecture/environment/constraints. Creating a project automatically queues selected official docs.
- All 29 catalog entries remain required for full release. The later GitHub extension supersedes current-docs-only scope: match official versioned docs where publishers provide them; unresolved versions and major/minor fallback require explicit choices, and unavailable docs stay unavailable.
- PDF/TXT/Markdown/DOCX private documents; explicit approval for every external processor of private context/content.
- Persistent author-private project conversations across reload/login/restart. Each conversation fixes its answer provider.
- **User rejected standalone questions and later rejected a hard chat-length cutoff.** Each turn uses current project context/history; summarize older context under explicit numeric token limits. Full transcript stays stored.
- Answer providers: **Gemini, Groq, Hugging Face hosted inference**. Groq is not Grok. Local HF was not selected.
- Approved retrieval change: Gemini embeddings plus bounded Gemini **LLM reranking**, replacing the draft HF embedding/cross-encoder proposal. Gemini retrieval approval is required even for Groq/HF answers.
- Clarifying replies are supported. Accepted turns are durable/background/recoverable; no silent duplicate paid replay on reload/checkpoint recovery.
- Revoked/deleted remembered sources pause affected conversations; messages/summaries/checkpoints cannot bypass policy. New conversation does not inherit contaminated memory.
- Global US$20/month paid-API ceiling plus operator workspace caps; tenants see own usage, not global/other-tenant spending.
- Light/dark toggle: initially OS preference, per-device override, consistent surfaces/native controls/code/evidence/dialogs.
- Conversations and cited snapshots remain until explicit deletion. Immediate access removal, 24-hour local cleanup while services run, seven-day backup expiry, 90-day content-free audit retention; overdue cleanup before traffic after downtime.
- 150 scenarios including multi-turn behavior, 100 development/50 held-out, distinct 30-output development and release human-review samples.
- Each milestone includes builder explanation/failure walkthrough. Only the user approves reductions in accepted scope/quality criteria.

## Confirmed GitHub extension

- Optional user-owned read-only GitHub App connection, separate from login; selected repositories and current upstream viewer/actor access are required for private repo-derived knowledge.
- One repository or selected monorepo application per project; branch selection defaults to default branch; each scan pins one commit. No application source-code ingestion, cloning, installs, or executable config evaluation.
- Python/JavaScript/TypeScript static metadata detection. Declarations: requirements.txt, standard pyproject.toml, package.json. Initial resolved lockfiles: uv.lock, package-lock.json, pnpm-lock.yaml; unsupported formats stay explicit.
- Direct runtime dependencies preselected, dev tools optional, transitive-only docs not auto-imported. User reviews/corrects stack before imports. Goal remains user-provided.
- Catalog-first docs, then publisher-linked candidate discovery. New origin/path scopes require project/workspace review; version fallbacks require explicit acceptance. No automatic promotion to global catalog.
- Private/local/Git/unresolved dependency lookups require explicit consent. Persist normalized facts/minimal redacted provenance; do not forward raw configs/credentials/private URLs.
- Manual rescans show diffs and update approved context only after acceptance. No automatic push sync/webhook relay in initial scope. Loss of upstream access applies to retained analysis and dependent conversation memory.

## Explicit engineering defaults

React/TypeScript/Vite; FastAPI; PostgreSQL/pgvector; Procrastinate queues; protected LangGraph/PostgreSQL checkpoints; Keycloak brokers/email flows; restricted parser; optional local operational dashboard profile.

The user explicitly selected uv for backend dependencies and incremental dependency updates. Backend metadata currently requires Python 3.12+ and has no dependencies. Frontend uses npm; add packages only when a task needs them and synchronize the relevant manifest/lockfile.

Answer input cap 24,000 tokens including 12,000 memory tokens; older summary up to 2,000 within memory; final evidence up to 6,000. No arbitrary turn-count cap. Architecture owns helper budgets, limits, model candidates, and initial unmeasured quality/performance targets.

New workspaces require an operator-assigned spending allowance; project/import state can wait visibly. Local SMTP capture supports tests; actual email delivery/OAuth brokers require configuration. Specific model IDs/backends/prices remain public-doc candidates until budget-reserved probes.

## Work actually performed

- Created and refined the six Markdown planning files; preserved original portfolio specifications.
- Read Superpowers brainstorming/writing-plans, frontend-design, web-design-guidelines, writing-for-agents, and explicitly invoked grilling guidance.
- Fresh reviewers stress-tested product/system, frontend, and delivery/handoff; public primary-doc research covered memory, identity, model/pricing alternatives, and theme contrast.
- Reconciled the confirmed conversation/tenant/auth/theme/provider/budget/retention/evaluation/delivery decisions across all six files.
- Replaced the milestone-only tasks draft with an implementation plan, including file ownership, interfaces, test cycles, verification commands, learning checks, and a vertical-first dependency order.
- Added the confirmed GitHub extension across all six files: access/data/source boundaries, parser/version contracts, frontend scan/review/rescan flows, and connector/discovery tasks. No GitHub account/repository was connected or scanned.
- Extension structural checks passed for six files, local links/fences, 29 catalog entries, twelve ordered unchecked implementation tasks. Fresh review identified requirements-file role ambiguity and an overly narrow fetch-authority sentence; clarified unknown roles/constraint-only handling and immutable external approvals under the same network guards. These are documentation clarifications, not executed runtime tests.
- Before the GitHub extension, structural validation passed for the six files, local links/titles, fences, 29 entries, and ten tasks; a fresh builder reported no material planning gaps. That review predates the extension and is not claimed as its verification.
- Initialized the backend source/migrations/test-fixture directories, feature-oriented frontend folders, catalog/evaluation homes, infrastructure configuration, operational docs, and future CI directory. Added empty .gitkeep files, root README, and .gitignore; kept all six planning files in place.
- Scaffold validation confirmed all 24 intended leaf directories and empty placeholders, valid local Markdown links/fences, and no application code, package manifests, or Git repository. This was a filesystem/document check, not a runtime test.
- At the user's request, moved the six planning Markdown files into docs/, leaving README.md at the root. Updated relative links/provenance paths and the root folder map; backend/ and frontend/ remain separate application roots communicating through the HTTP API.
- Subsequently moved catalog/, eval/, and infra/ under backend/ as requested. Updated README, implementation paths, backend ownership rules, and the generated-report ignore/placeholder exception. No application code or configuration content was introduced.
- Created backend/pyproject.toml with empty dependencies. Initialized the official Vite React/TypeScript starter in frontend/, retained feature folders, and placed startup code in src/app/ and global CSS in src/styles/. The page is a minimal placeholder, not the planned product interface.
- Installed only the frontend starter dependencies and generated package-lock.json. The TypeScript/Vite production build and Oxlint check passed. Python tomllib parsed backend metadata; checks confirmed frontend manifest/lockfile consistency, retained feature folders, and no backend lockfile or Git initialization. Browser rendering and uv sync were not checked; uv is not currently on PATH.
- Updated root .gitignore for Vite caches/temporary config, SSR output, npm cache, and local overrides. Git check-ignore verified twelve generated/private paths ignored and fifteen source/config/docs paths trackable, including manifests, lockfiles, .env.example, and all six planning files. Used disposable metadata; the project remains without a Git repository.
- No backend runtime, product features, Git initialization, migrations, account setup, paid calls, commits, or deployment have been executed. Existing implementation task checkboxes remain unchecked.

## Verification and remaining risks

- On 2026-10-29, wrote the draft OpenAPI 3.1.1 contract and API usage guide at the user's request, covering 50 paths/69 operations and 79 schemas. Linked them from README/architecture/tasks. Documented sessions/CSRF, roles/grants/processor policies, private durable turns/retry uncertainty, source/version approvals, GitHub scans/reviews, uploads, citations, own-tenant usage, and deletion. Proposed wire choices remain labeled draft; no backend/application dependency or feature was added, and implementation checkboxes remain unchecked.
- Official OpenAPI 3.1 structural-schema validation passed, as did duplicate-key/reference/operation-ID/path-parameter/mutation-security/schema checks and 32 valid/invalid payload/example checks. Validation used already-available Python YAML/JSON Schema tooling and a read-only fetch of the official public schema; no project content was uploaded. All 32 local Markdown links in the five affected Markdown files resolved; code fences and whitespace checks passed. No live API, auth, provider, database, browser, or runtime authorization behavior was tested.
- A clean Git repository with initial commit `c7f1f4d` was already present when this documentation session began. Earlier no-Git notes above describe the earlier scaffold sessions. This session did not initialize Git, commit, push or deploy.

- Prior structural checks covered exactly six filenames, local links, fences, and 29 catalog entries. Theme solid-color contrast was calculated; rendered browser accessibility/performance remains untested.
- Docker executable exists, but engine readiness/capacity and reference hardware were not verified; CIM hardware inspection was unavailable.
- Public docs support candidate hosted profiles and token-priced Gemini retrieval. Actual account availability, adapter/tokenizer/output/price behavior, OAuth/SMTP/GitHub App setup, source manifests/license/robots/locators, parser/lock schemas, upstream checks, and documentation-version mappings remain verification gates.
- Older public cost estimates were illustrative workloads, not measured bills. Updated estimates must include actual multi-turn, summary, query-resolution, reranking, judging, retry, and re-index counts.
- Held-out data must not be used for provider selection/calibration; review labels separately from generated outputs.
- Local retention cannot recall dispatched provider data, and a powered-off machine cannot perform cleanup; startup reconciliation and provider-retention disclosure are required.

## Next action

Folder scaffolding, frontend initialization, and draft API documentation are complete; continue product/backend work when the user requests the next step. Review the draft wire contract as the owning backend tasks are implemented. Preserve the confirmed scope and GitHub extension; do not reintroduce current-docs-only/catalog-only discovery, full repository code RAG, shared GitHub credentials, blind version guesses, standalone questions, light-only UI, browser-bound turns, per-turn provider changes, HF cross-encoder requirements, or demo-only tenancy.

After substantive work, update actual task checkboxes/evidence and this handoff. Keep unverified behavior labeled honestly; do not infer implementation from a completed planning session.
