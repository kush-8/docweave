"""Refresh serialized jobs and derive catalog coverage from published indexes."""
from alembic import op
revision='0018_personal_job_context'
down_revision='0017_personal_retrieval'
branch_labels=None
depends_on=None
FUNCTIONS={
'app.personal_job_context(uuid,uuid)':r"""
CREATE FUNCTION app.personal_job_context(p_id uuid,p_token uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.personal_jobs%ROWTYPE; c app.conversations%ROWTYPE; p app.projects%ROWTYPE;
BEGIN
 SELECT * INTO j FROM app.personal_jobs WHERE id=p_id AND status='running' AND lease_token=p_token AND lease_expires_at>now() FOR UPDATE;
 IF j.id IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO c FROM app.conversations WHERE id=j.conversation_id AND deleted_at IS NULL;
 SELECT * INTO p FROM app.projects WHERE id=c.project_id AND owner_user_id=j.actor_id;
 IF p.id IS NULL OR NOT EXISTS(SELECT 1 FROM app.auth_sessions WHERE user_id=j.actor_id AND expires_at>now()) THEN RETURN NULL; END IF;
 PERFORM set_config('docweave.actor_id',j.actor_id::text,true);
 UPDATE app.personal_jobs SET lease_expires_at=now()+interval '10 minutes' WHERE id=p_id;
 IF j.kind='answer' THEN UPDATE app.turns SET context_revision=p.context_revision WHERE id=j.turn_id; END IF;
 RETURN jsonb_build_object('project',app.personal_project(p.id),'stack_fingerprint',p.stack_fingerprint,'turn',app.personal_turn(j.turn_id));
END $$""",
'app.personal_catalog_state(uuid,uuid,uuid)':r"""
CREATE FUNCTION app.personal_catalog_state(p_job uuid,p_token uuid,p_generation uuid) RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF app.personal_job_context(p_job,p_token) IS NULL THEN RETURN; END IF;
 RETURN QUERY SELECT to_jsonb(r)||jsonb_build_object('revision_id',r.id,'eligible',r.enabled AND r.source_approved,
 'generation_id',p_generation,'indexed_generation_id',CASE WHEN EXISTS(
 SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id
 WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id)
 ) THEN p_generation ELSE NULL END,
 'status',CASE WHEN EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id
 WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id))
 THEN 'indexed' ELSE 'missing' END,'active_job',false)
 FROM app.public_catalog_revisions r WHERE r.enabled AND r.source_approved;
END $$""",
'app.personal_select_catalog(uuid,uuid,jsonb)':r"""
CREATE FUNCTION app.personal_select_catalog(p_job uuid,p_token uuid,p_choices jsonb) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE context jsonb; project uuid; choice jsonb;
BEGIN
 context:=app.personal_job_context(p_job,p_token);
 IF context IS NULL THEN RETURN false; END IF;
 project:=(context->'project'->>'id')::uuid;
 IF jsonb_typeof(p_choices)<>'array' OR jsonb_array_length(p_choices)>10000 THEN RAISE EXCEPTION 'Invalid selection' USING ERRCODE='22023'; END IF;
 DELETE FROM app.project_catalog_selections s WHERE s.project_id=project AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(context->'project'->'stack') d WHERE d->>'id'=s.dependency_id);
 FOR choice IN SELECT * FROM jsonb_array_elements(p_choices) LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(context->'project'->'stack') d JOIN app.public_catalog_revisions r ON r.id=(choice->>'revision_id')::uuid WHERE d->>'id'=choice->>'dependency_id' AND lower(d->>'technology')=lower(r.technology) AND r.enabled AND r.source_approved
  AND r.coverage->>'granularity'='exact' AND d->>'docs_target'=r.coverage->>'version') THEN CONTINUE; END IF;
  INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id) VALUES(project,choice->>'dependency_id',(choice->>'revision_id')::uuid)
  ON CONFLICT(project_id,dependency_id) DO UPDATE SET catalog_revision_id=excluded.catalog_revision_id,fallback_accepted=false;
 END LOOP;
 RETURN true;
END $$""",
}

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime')
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')

def downgrade():
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
