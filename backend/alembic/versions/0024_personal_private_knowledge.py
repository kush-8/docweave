"""Reuse private ingestion under direct ownership and assess every published version."""
from alembic import op
import importlib.util
from pathlib import Path
revision='0024_personal_private_knowledge'
down_revision='0023_personal_configuration'
branch_labels=None
depends_on=None
FUNCTIONS={
'app.personal_resource(text,uuid)':r"""
CREATE FUNCTION app.personal_resource(p_kind text,p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('project_id',p.id,'workspace_id',p.workspace_id) FROM app.projects p JOIN app.collections c ON c.project_id=p.id
 WHERE app.personal_project_owned(p.id) AND ((p_kind='project' AND p.id=p_id) OR(p_kind='collection' AND c.id=p_id)
 OR(p_kind='document' AND EXISTS(SELECT 1 FROM app.documents d WHERE d.id=p_id AND d.collection_id=c.id AND d.deleted_at IS NULL))
 OR(p_kind='source' AND EXISTS(SELECT 1 FROM app.sources s WHERE s.id=p_id AND s.collection_id=c.id AND s.deleted_at IS NULL))
 OR(p_kind='job' AND EXISTS(SELECT 1 FROM app.ingestion_jobs j JOIN app.documents d ON d.id=j.document_id WHERE j.id=p_id AND d.collection_id=c.id AND d.deleted_at IS NULL))) LIMIT 1
$$""",
'app.assess_ingestion_version(uuid,jsonb)':r"""
CREATE FUNCTION app.assess_ingestion_version(p_version uuid,p_assessment jsonb) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE v app.document_versions%ROWTYPE; d app.documents%ROWTYPE;
BEGIN
 SELECT * INTO v FROM app.document_versions WHERE id=p_version;
 SELECT * INTO d FROM app.documents WHERE id=v.document_id;
 IF v.id IS NULL OR d.deleted_at IS NOT NULL OR NOT app.collection_can(d.collection_id,'write') OR p_assessment->>'document_version'<>v.id::text OR p_assessment->>'content_hash'<>v.content_hash OR p_assessment->>'rule_revision'<>'deterministic-v1' THEN RETURN false; END IF;
 INSERT INTO app.document_assessments(document_version_id,content_hash,parser_config_hash,rule_revision,credential_blocked,injection_flagged,complete)
 VALUES(v.id,v.content_hash,p_assessment->>'parser_config_hash',p_assessment->>'rule_revision',(p_assessment->>'credential_blocked')::boolean,(p_assessment->>'injection_flagged')::boolean,(p_assessment->>'complete')::boolean)
 ON CONFLICT(document_version_id) DO UPDATE SET content_hash=excluded.content_hash,parser_config_hash=excluded.parser_config_hash,rule_revision=excluded.rule_revision,credential_blocked=excluded.credential_blocked,injection_flagged=excluded.injection_flagged,complete=excluded.complete,reviewed_by=NULL;
 IF NOT app.personal_assessment_eligible(v.id) THEN UPDATE app.documents SET status='quarantined' WHERE id=d.id; END IF;
 RETURN true;
END $$""",
'app.personal_review_document(uuid,uuid,text,text)':r"""
CREATE FUNCTION app.personal_review_document(p_document uuid,p_version uuid,p_hash text,p_rules text) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE assessment app.document_assessments%ROWTYPE;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM app.documents d JOIN app.collections c ON c.id=d.collection_id WHERE d.id=p_document AND d.active_version_id=p_version AND d.deleted_at IS NULL AND app.personal_project_owned(c.project_id)) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 SELECT * INTO assessment FROM app.document_assessments WHERE document_version_id=p_version FOR UPDATE;
 IF assessment.document_version_id IS NULL OR assessment.content_hash<>p_hash OR assessment.rule_revision<>p_rules OR p_rules<>'deterministic-v1' OR NOT assessment.complete OR assessment.credential_blocked THEN RAISE EXCEPTION 'Review cannot waive block' USING ERRCODE='22023'; END IF;
 UPDATE app.document_assessments SET reviewed_by=nullif(current_setting('docweave.actor_id',true),'')::uuid WHERE document_version_id=p_version;
 UPDATE app.documents SET status='waiting_capacity' WHERE id=p_document;
 RETURN true;
END $$""",
}

def prior(name):
 spec=importlib.util.spec_from_file_location('prior_'+name,Path(__file__).with_name(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  role='docweave_worker' if signature.startswith('app.assess_ingestion_version') else 'docweave_runtime'
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {role}')
 original=prior('0006_collection_policy')
 # This migration's SQL is inline; use its established policy predicate as the legacy branch.
 op.execute(r"""CREATE OR REPLACE FUNCTION app.collection_can(p_collection uuid,p_action text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.collections c WHERE c.id=p_collection AND c.project_id IS NOT NULL AND (
 (app.personal_project_owned(c.project_id) AND p_action IN ('read','write','manage')) OR
 (c.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid AND EXISTS(SELECT 1 FROM app.memberships m WHERE m.workspace_id=c.workspace_id AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid AND (
 (m.role='owner' AND p_action IN ('read','write','manage')) OR (p_action='read' AND EXISTS(SELECT 1 FROM app.collection_grants g WHERE g.collection_id=c.id AND g.user_id=m.user_id)) OR (p_action='write' AND m.role='maintainer' AND EXISTS(SELECT 1 FROM app.collection_grants g WHERE g.collection_id=c.id AND g.user_id=m.user_id AND g.access='write')))))))
 $$""")
 module=prior('0008_ingestion')
 for signature in ('app.selection_for_import(uuid,uuid)','app.enqueue_ingestion(uuid,uuid,uuid,text,text,text,text,uuid,uuid)'):
  if signature not in module.FUNCTIONS: continue
  sql=module.FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace('c.workspace_id=ds.workspace_id','c.workspace_id IS NOT DISTINCT FROM ds.workspace_id').replace('ds.workspace_id=w','ds.workspace_id IS NOT DISTINCT FROM w')
  op.execute(sql)

def downgrade():
 module=prior('0008_ingestion')
 for signature in ('app.selection_for_import(uuid,uuid)','app.enqueue_ingestion(uuid,uuid,uuid,text,text,text,text,uuid,uuid)'):
  if signature in module.FUNCTIONS:op.execute(module.FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 # The prior legacy-only predicate remains represented in its original migration; direct ownership cannot be safely downgraded with retained personal data.
 for signature in reversed(FUNCTIONS):op.execute(f'DROP FUNCTION {signature}')
