-- Explicit operator-reviewed text source, scoped to an existing project and its current owner.
-- psql -v ON_ERROR_STOP=1 -v workspace_id=... -v project_id=... -v approved_by=... -f this-file.sql
BEGIN;
SELECT set_config('docweave.actor_id', :'approved_by', true),
       set_config('docweave.workspace_id', :'workspace_id', true);
SELECT app.lock_workspace_owner();
SELECT app.project_view(:'project_id'::uuid);
INSERT INTO app.documentation_selections(
    id,workspace_id,project_id,approved_by,technology,docs_target,coverage,source_url,origin,path_prefix,attribution)
VALUES (
    md5(:'project_id' || ':pilot-fastapi-2026-10-31')::uuid,
    :'workspace_id'::uuid, :'project_id'::uuid, :'approved_by'::uuid,
    'FastAPI', 'rolling:2026-10-31', '{"granularity":"rolling","publisher_range":null}',
    'https://raw.githubusercontent.com/fastapi/fastapi/1c83302d783783d4c9703df94b823dd39e545b63/docs/en/docs/tutorial/sql-databases.md',
    'https://raw.githubusercontent.com',
    '/fastapi/fastapi/1c83302d783783d4c9703df94b823dd39e545b63/docs/en/docs/tutorial/',
    'FastAPI documentation; MIT license; https://github.com/fastapi/fastapi/blob/1c83302d783783d4c9703df94b823dd39e545b63/LICENSE')
-- Reruns neither duplicate the approval nor reactivate a revoked selection.
ON CONFLICT (id) DO NOTHING;
COMMIT;
