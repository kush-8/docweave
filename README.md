# DocWeave

Project-aware technical documentation and knowledge assistant.

Status: React/TypeScript/Vite frontend starter and an empty uv backend manifest are initialized. Product features, backend runtime, migrations, containers, and Git initialization remain future work.

## Repository structure

```text
docweave/
├── README.md
├── backend/
│   ├── src/docweave/             # Python application and domain modules
│   ├── pyproject.toml            # uv-managed Python project metadata/dependencies
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

Planning and operational Markdown live in `docs/`; this introduction stays at the project root. The user authorized the folder structure, backend manifest, and frontend starter. None of the implementation milestones are complete.

## Local development

Use Node.js 22.12+ for the frontend. From `frontend/`, run `npm ci` to install the locked dependencies, `npm run dev` to start Vite, `npm run build` to type-check and build, and `npm run lint` to lint.

The frontend starts with a minimal placeholder page; the planned product interface is not implemented. Backend dependencies are managed with uv and are currently empty. Add dependencies only as the task needs them, keeping each application's manifest and lockfile in sync.
