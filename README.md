# DocWeave

A personal, GitHub-linked technical documentation assistant and AI engineering project.

Sign in with GitHub, connect a repository/branch/application folder, provide a short goal, and start project-bound chats. New chats check commit-pinned dependency metadata. Trusted, version-matching public documentation can be indexed once and reused across projects; repository facts, uploads and conversations remain private.

Current checkpoint: the personal API, workers, shared catalog/index scope, guardrail boundaries and frontend are implemented and exercised with disposable PostgreSQL and mocked provider HTTP. The full refactor is **not yet release-complete**. Real account verification, preserved-development-data cutover and the remaining product/reliability work are listed in the [checkpoint report](docs/reports/2026-11-01-personal-projects-checkpoint.md).

Retrieval remains hybrid: keyword search (native full text/BM25) plus vector search (exact/HNSW), RRF fusion and Groq reranking. The personal worker currently defaults to BM25 plus exact vector search; these are provisional operational choices, not a claim of a benchmark winner. Gemini embeddings, Groq LLM roles, processor consent, source/version eligibility, credential blocking and citation validation remain. Semantic answer caching is not enabled.

## Repository

```text
docweave/
  backend/
    src/docweave/       # Current API, workflows, SQL, workers, RAG and evaluation
    alembic/versions/   # Immutable schema migrations and additive personal changes
    tests/             # Seven subsystem suites plus support and fixtures
    eval/              # Controlled inputs and ignored generated reports
    infra/             # PostgreSQL, isolated parser and operational configuration
  frontend/
    src/               # React components, hooks, routing and API client
    tests/             # e2e, architecture and support fixtures
  docs/                # Current specifications, tasks and runbooks; history in memory.md
  logs/development/    # Ignored local execution logs
  storage/             # Ignored private artifacts
  backups/             # Ignored private backups
```

The current production application contains no workspace/member/invitation/grant routes, Google/email login or Keycloak/Mailpit services. Retired handlers, test application, identity configuration and obsolete SaaS endpoint tests are deleted. Legacy database rows, models and migration functions remain deliberately preserved pending validated cutover; they do not constitute a collaboration product.

## Run and verify

See the [personal-project runbook](docs/runbooks/personal-projects.md) before enabling accounts or migrating existing data. Copy `.env.example` only when creating a new environment; preserve an existing `.env`. Configure a GitHub App with read-only Contents and Metadata permissions, selected repositories, the correct callback and a backend-only client secret/encryption key.

```powershell
uv sync --project backend --locked
uv run --project backend --locked uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 58000 --no-access-log --no-proxy-headers
```

Run `npm ci`, then `npm run dev` from `frontend/` (Node.js 22.12+). Vite proxies `/api` to port 58000; local `APP_ORIGIN` must match the browser's frontend origin. No private state is persisted in browser storage.

The ingestion worker is `python -m docweave.worker`; the personal conversation/shared-catalog worker is `python -m docweave.workers.personal`, using the backend source environment. Normal hosted processing requires explicitly configured immutable generation/profile IDs, verified account/capability/pricing and current processing approvals. API keys alone do not enable processing. Do not run paid work merely to test configuration.

Start only the disposable database for tests:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests -q -W error
```

See [backend test organization](backend/tests/README.md) and [frontend tests](frontend/tests/README.md). Backend DB tests must run serially. Frontend verification uses `npm run build`, `npm run lint`, and `npm test`; installed Chrome can be selected with `PLAYWRIGHT_CHANNEL=chrome`.

`/docs` and `/openapi.json` describe the running API; `backend/openapi.yaml` contains its checked personal contract. The obsolete contract fixture is removed. Liveness is available; readiness remains 503 until release requirements are satisfied.

Read [memory](docs/memory.md), [PRD](docs/PRD.md), [rules](docs/rules.md), the [approved personal-project plan](docs/superpowers/plans/2026-10-31-personal-github-projects.md), and the [remaining-task report](docs/reports/2026-11-01-personal-projects-checkpoint.md) for current work. Superseded documentation and measurements are retained only in docs/memory.md.
