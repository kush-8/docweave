# Backend tests

Run from the repository root:

```powershell
uv run --project backend --locked pytest backend/tests -q -W error
```

All database tests use explicitly configured, guarded `docweave_test` on port 55433. Run database suites serially; fixtures migrate and clear this disposable database. Never point tests at development. External model calls are mocked unless an explicitly authorized operator command says otherwise.

| Directory | Coverage |
| --- | --- |
| api | Current HTTP contract, health, safe errors and architectural boundaries |
| database | Migrations, schema, isolation and development-recovery safeguards |
| github | Read-only App transport, OAuth/session lifecycle and static repository scanning |
| personal | Direct ownership, project memory, real personal HTTP/worker/RAG workflows |
| rag | Ingestion, parsers, retrieval, fusion, guardrails, catalog and shared indexing |
| providers | Provider contracts, admission, compatibility and probe boundaries |
| evaluation | Reproducible datasets, public fixtures, reports and fingerprints |
| fixtures | Public/synthetic inputs and retained licenses |
| support | Current GitHub application fixtures and focused shared helpers |

`tests.paths` owns stable repository/backend/fixture locations. Test imports use their package paths; moving a suite must not require modifying `sys.path` or copying fixtures. Shared pytest defaults remain in `conftest.py`.

No copied retired application or obsolete workspace/OIDC endpoint tests remain. Ingestion/retrieval/evaluation fixtures exercise the current GitHub application with direct-owner API-created projects. Retained database/financial tests cover actively referenced schema and preservation/accounting functions; they do not mount retired product endpoints.
