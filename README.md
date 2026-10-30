# DocWeave

Project-aware technical documentation and knowledge assistant.

Status: The frontend remains a synthetic preview. The backend implements Keycloak OIDC, workspaces/memberships, manual projects, collection grants, processor consent, configured answer profiles, conservative budgets/usage and durable bounded TXT/Markdown ingestion. Uploads and operator-approved single-page sources prepare immutable local snapshots through a restricted queue worker; indexing and hosted AI remain unavailable. Profiles/prices/account capabilities remain unverified and disabled. Readiness, conversations and GitHub setup remain incomplete; frontend integration is deferred. See the [auth](docs/runbooks/auth.md), [workspace](docs/runbooks/workspaces.md), [membership](docs/runbooks/memberships.md), [project](docs/runbooks/projects.md), [collection policy](docs/runbooks/collection-policy.md), [budget](docs/runbooks/budget.md) and [ingestion](docs/runbooks/ingestion.md) runbooks.

Current RAG plan: Groq-hosted LLMs with Gemini embeddings; compare native full-text/BM25 and filtered exact/HNSW retrieval through an end-to-end RAG evaluation pipeline. These paths remain planned. See the [backend task order](docs/tasks.md#current-backend-task-order--2026-10-30); frontend integration and the future provider-selecting LLM gateway are deferred.

## Repository structure

```text
docweave/
├── README.md
├── backend/
│   ├── src/docweave/             # Python application and domain modules
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
│   │   ├── app/                 # Routes, application bootstrap, providers
│   │   ├── features/
│   │   │   ├── auth/            # Login/session UI
│   │   │   ├── workspaces/      # Tenant switching, membership, invitations
│   │   │   ├── projects/        # Project setup and context settings
│   │   │   ├── knowledge/       # Collections, sources, documents, approvals
│   │   │   ├── conversations/   # Ask, history, composer, citation inspector
│   │   │   └── github/          # Connections, repository scans, stack review
│   │   ├── components/ui/       # Shared presentational controls
│   │   ├── lib/                 # Shared HTTP/browser utilities
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

- Backend domain routes and schemas stay close to the modules named in [tasks.md](docs/tasks.md). Backend source, migrations, dependencies, and tests belong inside `backend/`.
- Frontend source, assets, dependencies, and browser tests belong inside `frontend/`. Features own their pages/state; shared controls are presentational and cross-feature HTTP helpers belong in `lib`.
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

Open [interactive API docs](http://127.0.0.1:58000/docs) or [runtime OpenAPI](http://127.0.0.1:58000/openapi.json). Liveness returns 200; readiness remains 503. Configure [auth](docs/runbooks/auth.md) for login/session/logout, then use [workspace creation/listing](docs/runbooks/workspaces.md). Other domain handlers remain 501 after applicable session, CSRF and workspace-role checks. Public catalog/provider stubs remain 501. No jobs or AI calls are accepted. Responses carry request IDs, safe errors and `Cache-Control: no-store`.

## Backend tests

See the [database runbook](docs/runbooks/database.md) for credentials, persistent development PostgreSQL on port 55432, disposable tests on port 55433, migrations, and safe start/stop commands. Local credentials are in the ignored root `.env`; `.env.example` contains placeholders only. Database setup does not wire feature routes to persistence or make overall application readiness succeed.

From the DocWeave root, run `uv sync --project backend --locked`, start `docker compose --profile test up -d --wait test-db`, then run `uv run --project backend --locked pytest backend/tests -q`. From `backend/`, `uv run --locked pytest` discovers the full backend suite. Explicit test URLs are required; test-target guards reject the development instance.

The backend suite covers contracts, HTTP/auth boundaries, signed OIDC claims, real migrations, constraints, narrow runtime privileges, tenant RLS, pooled-context cleanup and disposable-target guards. The separate [local identity smoke](docs/runbooks/auth.md#verification-and-recovery) exercises captured-email registration, verification, reset and logout against Keycloak. No paid APIs are used. Full domain authorization and real social-provider compatibility remain future evidence; Windows sandbox execution may need local-loopback permission.

Backend development follows TDD: write and run failing runtime tests, implement only enough to pass them, then refactor while keeping the full suite green. The skeleton tests were written first and observed failing because the app was missing (75 failed, 70 passed); after implementation the suite passed all 145 tests, including with warnings treated as errors. The first liveness test is now GREEN. Continue feature behavior one test at a time; contract checks supplement this loop. See the [skeleton plan and evidence](docs/superpowers/plans/2026-10-29-api-skeleton.md).
