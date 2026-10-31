"""Direct-owner project API, without creating a replacement workspace layer."""
from alembic import op

revision='0015_personal_projects'
down_revision='0014_public_catalog'
branch_labels=None
depends_on=None

FUNCTIONS={
'app.personal_project(uuid)': r"""
CREATE FUNCTION app.personal_project(p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',p.id,'created_at',p.created_at,'name',p.name,'goal',p.goal,'stack',p.stack,
 'context_revision',p.context_revision,'architecture_notes',coalesce(p.architecture_notes,''),
 'environment',coalesce(p.environment,''),'constraints',coalesce(p.constraints,''),
 'sync_state',p.sync_status,'docs_state',CASE WHEN EXISTS(SELECT 1 FROM app.project_catalog_selections s WHERE s.project_id=p.id) THEN 'selected' ELSE 'missing' END,
 'default_collection_id',(SELECT id FROM app.collections WHERE project_id=p.id AND is_default),
 'repository',CASE WHEN p.repository_id IS NULL THEN NULL ELSE jsonb_build_object('repository_id',p.repository_id,
 'branch',p.repository_branch,'application_path',p.application_path,'commit_sha',p.last_commit_sha) END)
 FROM app.projects p WHERE p.id=p_id AND app.personal_project_owned(p.id)
$$""",
'app.personal_create_project(jsonb)': r"""
CREATE FUNCTION app.personal_create_project(p_body jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE actor uuid:=nullif(current_setting('docweave.actor_id',true),'')::uuid; project uuid;
BEGIN
 IF actor IS NULL OR NOT EXISTS(SELECT 1 FROM app.users WHERE id=actor) THEN RAISE EXCEPTION 'Identity required' USING ERRCODE='42501'; END IF;
 IF coalesce(p_body->>'goal','') !~ '[^[:space:]]' OR length(p_body->>'goal')>4000
 OR coalesce(p_body->>'name','') !~ '[^[:space:]]' OR length(p_body->>'name')>200
 OR coalesce(p_body->>'branch','') !~ '[^[:space:]]' OR length(p_body->>'branch')>255
 OR coalesce(p_body->>'repository_id','') !~ '^[1-9][0-9]{0,17}$'
 OR coalesce(p_body->>'application_path','') ~ '(^/|(^|/)\.\.(/|$)|\\|:)' THEN
 RAISE EXCEPTION 'Invalid project input' USING ERRCODE='22023'; END IF;
 INSERT INTO app.projects(owner_user_id,name,goal,repository_id,repository_branch,application_path,sync_status,architecture_notes,environment,constraints)
 VALUES(actor,p_body->>'name',p_body->>'goal',(p_body->>'repository_id')::bigint,p_body->>'branch',coalesce(p_body->>'application_path',''),'pending',p_body->>'architecture_notes',p_body->>'environment',p_body->>'constraints') RETURNING id INTO project;
 INSERT INTO app.collections(project_id,name,is_default) VALUES(project,'Default',true);
 RETURN app.personal_project(project);
END $$""",
'app.personal_link_repository(uuid,jsonb)': r"""
CREATE FUNCTION app.personal_link_repository(p_id uuid,p_body jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 PERFORM 1 FROM app.projects WHERE id=p_id AND app.personal_project_owned(id) FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 IF EXISTS(SELECT 1 FROM app.projects WHERE id=p_id AND repository_id IS NOT NULL) THEN RAISE EXCEPTION 'Binding is immutable' USING ERRCODE='40001'; END IF;
 IF coalesce(p_body->>'repository_id','') !~ '^[1-9][0-9]{0,17}$' OR coalesce(p_body->>'branch','') !~ '[^[:space:]]'
 OR length(p_body->>'branch')>255 OR coalesce(p_body->>'application_path','') ~ '(^/|(^|/)\.\.(/|$)|\\|:)'
 THEN RAISE EXCEPTION 'Invalid binding' USING ERRCODE='22023'; END IF;
 UPDATE app.projects SET repository_id=(p_body->>'repository_id')::bigint,repository_branch=p_body->>'branch',
 application_path=coalesce(p_body->>'application_path',''),sync_status='pending' WHERE id=p_id;
 RETURN app.personal_project(p_id);
END $$""",
'app.personal_list_projects(timestamptz,uuid,integer)': r"""
CREATE FUNCTION app.personal_list_projects(p_after timestamptz,p_id uuid,p_limit integer) RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT app.personal_project(p.id) FROM app.projects p WHERE app.personal_project_owned(p.id)
 AND (p_after IS NULL OR (p.created_at,p.id)>(p_after,p_id)) ORDER BY p.created_at,p.id LIMIT greatest(1,least(p_limit,101))
$$""",
}

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_worker')
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime')

def downgrade():
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
