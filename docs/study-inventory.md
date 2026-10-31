# Current code inventory

| Area | Location |
| --- | --- |
| Application/HTTP/security | `backend/src/docweave/api/` |
| Settings, identity, deterministic assessments | `backend/src/docweave/core/` |
| Schema, sessions, immutable migrations | `backend/src/docweave/db/`, `backend/alembic/versions/` |
| SQL persistence | `backend/src/docweave/repositories/` |
| Workflow/admission/catalog/ownership services | `backend/src/docweave/services/` |
| GitHub/static metadata/provider/source IO | `backend/src/docweave/integrations/` |
| Retrieval/indexing/prompt contracts | `backend/src/docweave/rag/` |
| Private artifacts/durable workers | `backend/src/docweave/storage/`, `backend/src/docweave/workers/` |
| Reproducible evaluation/corpus | `backend/src/docweave/evaluation/`, `backend/eval/`, `backend/tests/fixtures/ingestion/` |
| UI state/shell/components/navigation/HTTP | `frontend/src/{pages,layouts,components,hooks,routing,data}/` |
| Current subsystem tests | `backend/tests/`, `frontend/tests/` |

See [backend test guide](../backend/tests/README.md) and [frontend test guide](../frontend/tests/README.md). There is no executable legacy test application. Retained DB migration/financial compatibility code exists because current records and operator workflows still reference it, not to keep a SaaS product.

Python dependencies are declared in `backend/pyproject.toml` and pinned in `backend/uv.lock`; frontend dependencies in `frontend/package.json`/lockfile. Use `.env.example` for configuration names. Private `.env`, logs, backups, artifacts and generated reports are not learning inputs to publish.
