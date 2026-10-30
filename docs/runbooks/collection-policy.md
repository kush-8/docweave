# Collection access and processor consent

Backend-only APIs; no frontend integration, content ingestion, conversations or hosted AI calls are implemented by this slice. Start with [authentication](auth.md), a [workspace](workspaces.md) and a [manual project](projects.md). All mutations require the session cookie, exact Origin and `/me` CSRF token.

## Collections and grants

- `GET /api/v1/projects/{project_id}/collections`: current project members see only collections they can currently read. Owners see all. Pages use encrypted actor/project/resource-bound `(created_at,id)` cursors: 25 default, 100 maximum. `can_write` reflects the current role and grant, not a lasting authorization token.
- `POST /api/v1/projects/{project_id}/collections`: current owners supply `{ "name": "Manuals" }`; returns HTTP 201 with `{id, project_id, name, can_write}`. Names are trimmed/nonblank/NUL-free. New collections are owner-only, with no processor approvals. Creation of additional collections does not replace the project's default collection.
- `GET /api/v1/collections/{collection_id}/grants`: owners get `{revision, grants}`. The initial set is `{ "revision": 1, "grants": [] }`.
- `PUT` at the same grants path: owners supply the complete set plus its expected revision:

```json
{
  "expected_revision": 1,
  "grants": [{ "user_id": "00000000-0000-4000-8000-000000000003", "access": "read" }]
}
```

Use a real current workspace member ID. One entry per member; `write` includes read but requires owner/maintainer role. A member cannot gain write authority through a grant. Owners retain management authority without explicit entries. Empty grants restore owner-only access. Missing/other-tenant/nonmember/wrong-role assignments and malformed/duplicate/null/extra inputs return safe 422 without modifying the old set. A stale revision returns 409/`revision_conflict`; accepted replacements advance the grant revision once.

Membership removal deletes grants and advances affected revisions. Demotion to member changes write grants to read and advances affected revisions; later promotion does not restore write. Rejoining a workspace does not restore deleted grants. Role and grant mutations share the workspace lock, and functions recheck current ownership after waiting. Reads/pages reapply current access rather than trusting cursor contents.

Collection IDs do not grant access. Hidden, malformed and other-tenant IDs share 404. A visible nonowner receives 403/`forbidden` for management. Document stubs now require collection read/write authority before 501; actual uploads/listing remain unimplemented.

## Independent processor policies

GET/PUT these two paths:

- `/api/v1/projects/{project_id}/processing-policy`: current project members may read; owners replace.
- `/api/v1/collections/{collection_id}/processing-policy`: current collection readers may read; owners replace.

Each scope begins with its own `{ "revision": 1, "approved_processor_ids": [] }`. PUT requires a positive integer expected revision and the complete unique processor-ID list. Project, collection and grant revisions are independent of project context revision. Approving a processor at one scope does not approve it at another or add missing Gemini retrieval consent automatically. Unknown/disabled/brand-only IDs return 422. Empty lists always revoke all, including when prior IDs have been disabled. Stale revisions return 409. Policy reads keep authorization, revision and IDs in one database snapshot; consumers must revalidate current policy before external calls.

There are no conversations/workers to pause yet. Future hosted processing must check current membership/grants, both relevant policies, the exact actual processors, source/repository eligibility and reserved budget before dispatch and after relevant waits. No HTTP response or remembered approval is sufficient authority by itself.

## Operator processor metadata

`app.processors` is an operator-only registry of immutable IDs with provider, actual backend and role metadata. It starts empty. Runtime can read its nonsecret metadata but cannot register, repoint, enable or delete entries. Only the operator/migration connection may register reviewed identities; never store credentials, private URLs or content here. For example, after reviewing the real processor/backend, adapt this placeholder SQL:

```sql
INSERT INTO app.processors(id,provider,backend,roles,enabled)
VALUES ('reviewed-processor-id-v1','gemini','reviewed-actual-backend',
        '["embedding"]'::jsonb,true);
```

Providers are `gemini`, `groq` or `huggingface`; roles are `embedding`, `reranking`, `query_resolution`, `summarization` and `generation`. Record every actual serving processor, including a pinned Hugging Face backend. Registry identity fields cannot be updated/deleted; disable an ID with `UPDATE app.processors SET enabled=false WHERE id=...` and register a new ID for changed identity. Stored consent never silently follows a repointed ID. Enabling a registry row makes it eligible for consent only: it does not verify account/model capability, price, reservations or hosted-call availability. `/providers` remains reserved until that profile/admission work exists. Tests use synthetic `test:` metadata and no live providers.

## Storage, failure walkthrough and verification

Revision `0006_collection_policy` adds collection grant and project/collection processing revisions (default 1), composite tenant foreign keys, private RLS-enabled grant/approval tables, the registry, seven narrow runtime functions and two private invoker trigger helpers. No implicit grants/approvals are backfilled. Collection RLS uses current owner/grant/role facts; private approval rows are readable only through authorized policy projections. Ordinary domain DML remains denied. Membership reconciliation runs inside the same transaction as membership changes. Processor rows are locked during approval so a disable that wins a lock wait is observed before consent commits.

Failure walkthrough: two owners replace revision 1 concurrently. The first commits revision 2; the second sees 2 after its workspace lock wait and receives 409 without overwriting the winner. A database insert failure rolls back both deleted rows and the revision. Tests also force a read to wait while another transaction replaces policy/revokes a grant: a response cannot mix an old revision with newer processor IDs.

Tests use guarded disposable PostgreSQL only:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked --cache-dir backend/.uv-cache pytest backend/tests -q -W error --tb=short
docker compose --profile test stop test-db
```

Exact results/review are in the [plan](../superpowers/plans/2026-10-30-collection-policy.md). Development volumes were not started or migrated; restore their original credentials and inventory legacy stacks before persistent migration. Downgrading drops grants, approvals and processor registrations: it is not a data-preserving production rollback. Next backend task is budget admission and configured provider profiles, before approved-source ingestion or any paid calls.
