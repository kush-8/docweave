"""Revalidate retained evidence at history and citation release."""
from alembic import op
import importlib.util
from pathlib import Path
revision='0022_personal_release'
down_revision='0021_personal_provider_admission'
branch_labels=None
depends_on=None

FUNCTIONS={
'app.personal_citations_current(uuid,jsonb)':r"""
CREATE FUNCTION app.personal_citations_current(p_project uuid,p_citations jsonb) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE citation jsonb;
BEGIN
 IF NOT app.personal_project_owned(p_project) OR jsonb_typeof(p_citations)<>'array' THEN RETURN false; END IF;
 FOR citation IN SELECT * FROM jsonb_array_elements(p_citations) LOOP
  IF NOT EXISTS(SELECT 1 FROM app.chunks ch JOIN app.documents d ON d.id=ch.document_id JOIN app.collections c ON c.id=d.collection_id
  LEFT JOIN app.sources s ON s.id=d.source_id LEFT JOIN app.documentation_selections ds ON ds.id=s.source_selection_id LEFT JOIN app.public_catalog_revisions r ON r.id=c.catalog_revision_id
  WHERE ch.id=(citation->>'chunk_id')::uuid AND ch.document_version_id=(citation->>'document_version_id')::uuid
  AND ch.generation_id=(citation->>'generation_id')::uuid AND ch.content=citation->>'excerpt'
  AND d.deleted_at IS NULL AND app.personal_assessment_eligible(ch.document_version_id)
  AND ((c.project_id=p_project AND(d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active)) OR(c.catalog_revision_id IS NOT NULL AND r.enabled AND r.source_approved AND s.deleted_at IS NULL AND ds.active))) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
END $$""",
'app.personal_citation(uuid,text)':r"""
CREATE FUNCTION app.personal_citation(p_turn uuid,p_citation text) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT value FROM app.turns t JOIN app.conversations c ON c.id=t.conversation_id,jsonb_array_elements(t.citations) value
 WHERE t.id=p_turn AND c.deleted_at IS NULL AND app.personal_citations_current(c.project_id,t.citations) AND value->>'id'=p_citation
$$""",
'app.personal_worker_history(uuid,uuid)':r"""
CREATE FUNCTION app.personal_worker_history(p_job uuid,p_token uuid) RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.personal_jobs%ROWTYPE; context jsonb;
BEGIN
 context:=app.personal_job_context(p_job,p_token);
 IF context IS NULL THEN RETURN; END IF;
 SELECT * INTO j FROM app.personal_jobs WHERE id=p_job;
 RETURN QUERY SELECT app.personal_turn(t.id) FROM app.turns t WHERE t.conversation_id=j.conversation_id AND t.id<>j.turn_id ORDER BY t.sequence;
END $$""",
'app.personal_worker_scopes(uuid,uuid,uuid)':r"""
CREATE FUNCTION app.personal_worker_scopes(p_job uuid,p_token uuid,p_generation uuid) RETURNS SETOF uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE context jsonb; project uuid;
BEGIN
 context:=app.personal_job_context(p_job,p_token);
 IF context IS NULL THEN RETURN; END IF;
 project:=(context->'project'->>'id')::uuid;
 PERFORM set_config('docweave.personal_project_id',project::text,true);
 RETURN QUERY SELECT id FROM app.collections WHERE app.personal_index_policy(id,p_generation);
END $$""",
'app.catalog_embedding_authorized(uuid,uuid,uuid)':r"""
CREATE FUNCTION app.catalog_embedding_authorized(p_job uuid,p_token uuid,p_profile uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.catalog_jobs j JOIN app.index_generations g ON g.id=j.generation_id JOIN app.provider_profiles p ON p.id=p_profile
 WHERE j.id=p_job AND app.catalog_job_authorized(p_job,p_token) AND p.role='embedding' AND p.model=g.model AND p.backend=g.backend
 AND p.processor_ids @> g.processor_ids AND g.processor_ids @> p.processor_ids AND app.profile_disabled_reason(p.id) IS NULL)
$$""",
'app.personal_profile(uuid)':r"""
CREATE FUNCTION app.personal_profile(p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',p.id,'model',p.model,'provider',p.provider,'role',p.role,'processor_ids',p.processor_ids,'available',app.profile_disabled_reason(p.id) IS NULL)
 FROM app.provider_profiles p WHERE p.id=p_id
$$""",
}

def prior(name):
 spec=importlib.util.spec_from_file_location('prior_'+name,Path(__file__).with_name(name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  if signature=='app.personal_citation(uuid,text)': op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime')
  elif signature!='app.personal_citations_current(uuid,jsonb)': op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')
 original=prior('0016_personal_conversations').FUNCTIONS['app.personal_turn(uuid)']
 original=original.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace("'message',t.message,'status',t.status,'answer',t.answer,'citations',t.citations", "'message',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.message ELSE '' END,'status',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.status ELSE 'blocked_policy' END,'answer',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.answer ELSE NULL END,'citations',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.citations ELSE '[]'::jsonb END")
 op.execute(original)
 finish=prior('0016_personal_conversations').FUNCTIONS['app.personal_finish_job(uuid,uuid,jsonb)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
 finish=finish.replace(""" ELSE
  IF p_result->>'status' NOT IN""", """ ELSE
  PERFORM set_config('docweave.actor_id',job.actor_id::text,true);
  IF NOT app.personal_citations_current(project.id,coalesce(p_result->'citations','[]')) THEN p_result:=jsonb_build_object('status','blocked_policy','progress','Evidence access changed before release.'); END IF;
  IF p_result->>'status' NOT IN""")
 op.execute(finish)

def downgrade():
 module=prior('0016_personal_conversations')
 for signature in ('app.personal_turn(uuid)','app.personal_finish_job(uuid,uuid,jsonb)'):
  op.execute(module.FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 for signature in reversed(FUNCTIONS): op.execute(f'DROP FUNCTION {signature}')
