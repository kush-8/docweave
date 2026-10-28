# DocWeave

Project-aware technical documentation and knowledge assistant.

Status: The React/TypeScript/Vite frontend has an interactive workbench preview built with Tailwind CSS and shadcn components. A tested FastAPI skeleton covers all 69 draft API operations. PostgreSQL/pgvector, core tables, migrations, and restricted database sessions are set up. Liveness works; readiness is unavailable and feature routes return 501. Authentication, API persistence, business logic, and AI remain future work.

## Repository structure

```text
docweave/
├── README.md
├── backend/
│   ├── src/docweave/             # Python application and domain modules
│   ├── pyproject.toml            # uv-managed Python project metadata/dependencies
│   ├── openapi.yaml              # Draft API contract; no routes implemented
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

This is a design contract derived from the confirmed architecture. The guide identifies proposed wire-format decisions. The running skeleton exposes its current behavior through `/docs` and `/openapi.json`; the draft YAML continues to describe future feature behavior.

## Local development

Use Node.js 22.12+ for the frontend. From `frontend/`, run `npm ci` to install the locked dependencies, `npm run dev` to start Vite, `npm run build` to type-check and build, and `npm run lint` to lint.

The frontend opens an explicitly labeled sample conversation. Select a citation to inspect its synthetic source, start a new conversation to review provider selection, or switch light/dark themes. Desktop evidence is adjacent; below 1200px it opens in a keyboard-contained sheet. Citation/conversation URLs support reload and browser history. Drafts stay in memory, with a discard warning when switching conversations. Only the non-sensitive theme preference is persisted.

Messages are not sent: submitting preserves the draft and explains that the backend/model must be connected. There is no authentication, indexing, provider approval, or durable conversation storage in this preview. The other project screens are labeled unavailable. shadcn components were obtained through its MCP and official CLI; a 21st.dev MCP was not available in this session.

Run `npx playwright install chromium` once, then `npm test` for browser and automated accessibility checks. To use an installed Chrome instead, set `PLAYWRIGHT_CHANNEL=chrome` (PowerShell: `$env:PLAYWRIGHT_CHANNEL='chrome'`) before `npm test`. The suite starts its own local Vite server. Screenshots and failure traces go in ignored `frontend/test-results/`. The implementation follows [design.md](docs/design.md); automated accessibility checks do not establish complete WCAG conformance or screen-reader usability.

Backend runtime dependencies include FastAPI/Uvicorn, SQLAlchemy/asyncpg, Alembic, and environment-file support. Runtime and dev dependencies are managed with uv and locked in `backend/uv.lock`. Add dependencies only as the task needs them, keeping each application's manifest and lockfile in sync.

## Run the API skeleton

From the DocWeave root, run `uv sync --project backend --locked`, then:

```powershell
uv run --project backend --locked uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 8000 --no-access-log
```

If uv is not on PATH but the synchronized environment exists, use `./backend/.venv/Scripts/python.exe -m uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 8000 --no-access-log` on Windows. The development tool used in this session is at `C:/Users/acer/AppData/Local/Temp/docweave-test-tools/bin/uv.exe`; no system-wide uv installation was made.

Open [interactive API docs](http://127.0.0.1:8000/docs) or [runtime OpenAPI](http://127.0.0.1:8000/openapi.json). `GET /api/v1/health/live` returns HTTP 200 with `{"status":"ok"}`. Readiness returns 503 because required services are absent. Every other draft operation returns 501/`not_implemented`; no requests create records, establish sessions, accept jobs, or call providers. Feature stubs do not yet parse or validate their request bodies. The shared responses include server-generated request IDs, safe errors, and `Cache-Control: no-store`. This skeleton does not implement authentication or authorize private resources.

## Backend tests

See the [database runbook](docs/runbooks/database.md) for credentials, persistent development PostgreSQL on port 55432, disposable tests on port 55433, migrations, and safe start/stop commands. Local credentials are in the ignored root `.env`; `.env.example` contains placeholders only. Database setup does not wire feature routes to persistence or make overall application readiness succeed.

From the DocWeave root, run `uv sync --project backend --locked`, start `docker compose --profile test up -d --wait test-db`, then run `uv run --project backend --locked pytest backend/tests -q`. From `backend/`, `uv run --locked pytest` discovers the full backend suite. Explicit test URLs are required; test-target guards reject the development instance.

The suite has 70 draft-contract checks, 75 runtime skeleton checks, and 51 database checks. The database checks exercise real migrations, constraints, transactions, SELECT-only privileges, tenant RLS, pooled-context cleanup, and disposable-target safeguards. API/contract checks remain runnable independently without PostgreSQL; full tests require the isolated test database and local credentials. No paid APIs are used. This does not prove full application authorization, idempotency, or provider behavior. On this Windows sandbox, tests need local loopback access for Python's internal event-loop socket pair; a normal local terminal provides it.

Backend development follows TDD: write and run failing runtime tests, implement only enough to pass them, then refactor while keeping the full suite green. The skeleton tests were written first and observed failing because the app was missing (75 failed, 70 passed); after implementation the suite passed all 145 tests, including with warnings treated as errors. The first liveness test is now GREEN. Continue feature behavior one test at a time; contract checks supplement this loop. See the [skeleton plan and evidence](docs/superpowers/plans/2026-10-29-api-skeleton.md).
