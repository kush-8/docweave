# DocWeave

Project-aware technical documentation and knowledge assistant.

Status: The frontend remains a synthetic preview. The backend implements authentication/tenancy, manual projects, collection grants/consent, conservative budgets, durable TXT/Markdown snapshots and scoped retrieval/evaluation. Native full-text/SQL BM25 and exact/shared-HNSW paths have deterministic and operator public-pilot evidence; general hosted project dispatch, billing verification and full answer quality remain incomplete. Readiness stays unavailable; conversations, GitHub setup and frontend integration remain unfinished. See [auth](docs/runbooks/auth.md), [workspaces](docs/runbooks/workspaces.md), [memberships](docs/runbooks/memberships.md), [projects](docs/runbooks/projects.md), [collection policy](docs/runbooks/collection-policy.md), [budget](docs/runbooks/budget.md), [ingestion](docs/runbooks/ingestion.md) and [retrieval/evaluation](docs/runbooks/retrieval.md).

Current RAG plan: Groq-hosted LLMs with Gemini embeddings; compare native full-text/BM25 and filtered exact/HNSW retrieval through an end-to-end RAG evaluation pipeline. The [operator public-fixture pilot](docs/runbooks/public-pilot.md) now has live evidence: all four reranked hybrids supported 10/10 development questions and passed controls under its separate US$1 cap. Human labels, private processing, billing verification and full answer evaluation remain unfinished; no production default is selected. See the [backend task order](docs/tasks.md#current-backend-task-order--2026-10-30).

Guardrails and the [structured prompt-writing rule](docs/rules.md#structured-prompt-writing-rule) are confirmed follow-up work: exact-version scanning/quarantine, owner review, credential blocking and validated evidence links. See the [guardrail plan](docs/superpowers/plans/2026-10-31-rag-guardrails.md). Implementation is pending; semantic caching and live guard models are outside the milestone.

## Repository structure

```text
docweave/
├── README.md
├── backend/
│   ├── src/docweave/
│   │   ├── api/                 # HTTP routes, dependencies, safe errors and middleware
│   │   ├── schemas/             # Request/response validation, grouped by domain
│   │   ├── services/            # Workflows and transaction coordination
│   │   ├── repositories/        # SQL; rag/ owns lexical/vector/index publication queries
│   │   ├── db/                 # Engines, tenant sessions and registered domain models
│   │   ├── core/               # Configuration, paths, identity, security and errors
│   │   ├── integrations/       # OIDC, approved-source fetching, parser and hosted adapters
│   │   ├── storage/            # Artifact filesystem operations
│   │   ├── workers/            # Queue lifecycle and recovery
│   │   ├── rag/                # Parsing, chunking, embeddings, indexing, retrieval,
│   │   │                       # fusion, reranking, tokenization, prompts and shared contracts
│   │   └── evaluation/         # Datasets, metrics, component/public-pilot runners and reports
│   ├── pyproject.toml            # uv-managed Python project metadata/dependencies
│   ├── openapi.yaml              # Auth and planned domain API contract
│   ├── alembic/versions/         # Database migration revisions
│   ├── tests/fixtures/           # Backend tests and synthetic fixtures
│   ├── catalog/                 # Versioned documentation-source manifests
│   ├── eval/
│   │   ├── fixtures/            # Synthetic evaluation inputs
│   │   └── reports/             # Generated local results; ignored by Git
│   └── infra/
│       ├── keycloak/            # Identity-provider configuration
│       ├── parser/              # Parser container/resource configuration
│       └── observability/       # Metrics, trace, dashboard configuration
├── frontend/
│   ├── package.json              # Frontend dependencies and dev/build/lint scripts
│   ├── package-lock.json         # Locked frontend dependency versions
│   ├── index.html                # Vite HTML entry point
│   ├── vite.config.ts            # React/Vite configuration
│   ├── src/
│   │   ├── app/                 # Application bootstrap and composition
│   │   ├── pages/               # Workbench screen coordination
│   │   ├── layouts/             # Shell, header and desktop/mobile sidebar
│   │   ├── components/          # Composer, conversation, evidence and dialogs
│   │   ├── components/ui/       # Shared presentational controls
│   │   ├── hooks/               # Navigation/draft protection, theme and media queries
│   │   ├── routing/             # URL parsing, building and view types
│   │   ├── data/                # Explicitly synthetic preview fixtures
│   │   └── styles/              # Global styles and light/dark theme tokens
│   ├── public/                  # Public static assets; never private documents
│   └── tests/fixtures/          # Browser tests and deterministic API fixtures
├── docs/
│   ├── PRD.md / architecture.md / design.md
│   ├── rules.md / tasks.md / memory.md
│   ├── api.md                   # API usage guide
│   ├── adr/                     # Architecture decisions
│   └── runbooks/                # Setup, recovery, deletion, operations
└── .github/workflows/           # Future CI workflows
```

## Boundaries

- Backend routes own HTTP behavior, services coordinate workflows, and repositories own SQL. Simple handlers may call repositories directly; there is no mandatory forwarding service. Schemas and ORM models have separate homes. Backend source, migrations, dependencies, and tests belong inside `backend/`.
- Frontend source, assets, dependencies, and browser tests belong inside `frontend/`. Pages coordinate screens, layouts render the shell, hooks own browser/state behavior, and components render their inputs. Preview data stays separate from URL handling.
- RAG stages share leaf contracts rather than importing one another's orchestration. Provider adapters own wire encoding/transport; repositories own database encoding. Approved-source fetching keeps its DNS/IP, robots, redirect and authorization safeguards together.
- Workflow callers own transactions and connections. Ingestion keeps its advisory lock on the same connection across processing; financial admission commits before provider dispatch. Database error codes become domain errors before the HTTP layer maps them to safe responses.
- The frontend consumes the backend's versioned HTTP API. Neither application imports the other's source modules.
- Identity, authorization, retrieval, providers, ingestion, memory, and worker behavior belong to the backend. Frontend visibility is not authorization.
- Backend-owned source manifests, evaluation inputs/reports, and supporting-service configuration live in `backend/catalog/`, `backend/eval/`, and `backend/infra/`. Infrastructure config does not duplicate business logic.
- Test/evaluation fixtures are public or synthetic. Runtime uploads, credentials, databases, backups, and private repository data stay outside tracked source and frontend public assets.
- Empty `.gitkeep` files preserve the layout for future version control. Replace them when real content is added.

## Start here

Read [memory.md](docs/memory.md), [PRD.md](docs/PRD.md), and [rules.md](docs/rules.md), then the relevant [architecture](docs/architecture.md), [frontend design](docs/design.md), and [implementation tasks](docs/tasks.md).

Planning, API usage, and operational documentation live in `docs/`; the OpenAPI contract lives in `backend/openapi.yaml`, and this introduction stays at the project root. The user authorized the folder structure, backend manifest, frontend starter, and API documentation. None of the implementation milestones are complete.

## API documentation

Read the [API guide](docs/api.md) for authentication, authorization, project/import flows, durable-turn recovery, citations, GitHub review, errors, usage, and deletion. [openapi.yaml](backend/openapi.yaml) defines the planned `/api/v1` operations and request/response schemas in OpenAPI 3.1.1 format. Open it in a compatible local viewer.

The guide distinguishes implemented authentication from planned domain behavior. `/docs` and `/openapi.json` describe actual runtime responses; the draft YAML also contains future domain contracts.

## Local development

Use Node.js 22.12+ for the frontend. From `frontend/`, run `npm ci` to install the locked dependencies, `npm run dev` to start Vite, `npm run build` to type-check and build, and `npm run lint` to lint.

The frontend opens a simple chatbot with an empty message box. Its toggleable sidebar has New chat, expandable Workspaces with nested chats, and Recent chats below. On mobile the sidebar opens as a drawer. The example chat demonstrates source links; sources open only when selected. Model choices live under Chat options. Workspace/chat/source URLs support reload and browser history. Drafts stay in memory, with a discard warning on New chat or workspace/chat switching. Only the non-sensitive theme preference is persisted.

Messages are not sent: submitting preserves the draft and explains that chat is not connected yet. Workspaces and chats are labeled examples; this preview has no authentication, indexing, provider approval, or durable conversation storage. Controls reuse the installed shadcn components. The welcome suggestions adapt the MIT-licensed 21st.dev Agent Elements Suggestions component to the existing Button and theme, without new dependencies; its license is retained in frontend/src/components/agent-elements/LICENSE.

Run `npx playwright install chromium` once, then `npm test` for browser and automated accessibility checks. To use an installed Chrome instead, set `PLAYWRIGHT_CHANNEL=chrome` (PowerShell: `$env:PLAYWRIGHT_CHANNEL='chrome'`) before `npm test`. The suite starts its own local Vite server. Screenshots and failure traces go in ignored `frontend/test-results/`. The implementation follows [design.md](docs/design.md); automated accessibility checks do not establish complete WCAG conformance or screen-reader usability.

Backend runtime dependencies include FastAPI/Uvicorn, SQLAlchemy/asyncpg, Alembic, and environment-file support. Runtime and dev dependencies are managed with uv and locked in `backend/uv.lock`. Add dependencies only as the task needs them, keeping each application's manifest and lockfile in sync.

## Run the API skeleton

From the DocWeave root, run `uv sync --project backend --locked`, then:

```powershell
uv run --project backend --locked uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 58000 --no-access-log --no-proxy-headers
```

If uv is not on PATH but the synchronized environment exists, use `./backend/.venv/Scripts/python.exe -m uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 58000 --no-access-log --no-proxy-headers` on Windows.

Open [interactive API docs](http://127.0.0.1:58000/docs) or [runtime OpenAPI](http://127.0.0.1:58000/openapi.json). Liveness returns 200; readiness remains 503. Configure [auth](docs/runbooks/auth.md), then use the implemented workspace/project/collection/budget and [ingestion](docs/runbooks/ingestion.md) operations. The configured answer-profile catalog is implemented; the source catalog and unfinished domains remain 501 after current authority checks. Local ingestion jobs are accepted; hosted inference is unavailable. Responses carry request IDs, safe errors and `Cache-Control: no-store`.

## Backend tests

See the [database runbook](docs/runbooks/database.md) for credentials, persistent development PostgreSQL on port 55432, disposable tests on port 55433, migrations, and safe start/stop commands. Local credentials are in the ignored root `.env`; `.env.example` contains placeholders only. Database setup does not wire feature routes to persistence or make overall application readiness succeed.

From the DocWeave root, run `uv sync --project backend --locked`, start `docker compose --profile test up -d --wait test-db`, then run `uv run --project backend --locked pytest backend/tests -q`. From `backend/`, `uv run --locked pytest` discovers the full backend suite. Explicit test URLs are required; test-target guards reject the development instance.

The backend suite covers contracts, HTTP/auth boundaries, signed OIDC claims, real migrations, constraints, narrow runtime privileges, tenant RLS, pooled-context cleanup and disposable-target guards. The separate [local identity smoke](docs/runbooks/auth.md#verification-and-recovery) exercises captured-email registration, verification, reset and logout against Keycloak. No paid APIs are used. Full domain authorization and real social-provider compatibility remain future evidence; Windows sandbox execution may need local-loopback permission.

Backend development follows TDD: write and run failing runtime tests, implement only enough to pass them, then refactor while keeping the full suite green. The skeleton tests were written first and observed failing because the app was missing (75 failed, 70 passed); after implementation the suite passed all 145 tests, including with warnings treated as errors. The first liveness test is now GREEN. Continue feature behavior one test at a time; contract checks supplement this loop. See the [skeleton plan and evidence](docs/superpowers/plans/2026-10-29-api-skeleton.md).
