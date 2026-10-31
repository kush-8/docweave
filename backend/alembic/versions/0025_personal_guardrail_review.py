"""Version-bound review and guarded private indexing."""
from alembic import op
import importlib.util
from pathlib import Path
revision='0025_personal_guardrail_review'
down_revision='0024_personal_private_knowledge'
branch_labels=None
depends_on=None
FUNCTIONS={
'app.personal_document_eligible(uuid)':r"""
CREATE FUNCTION app.personal_document_eligible(p_document uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.documents d WHERE d.id=p_document AND d.deleted_at IS NULL AND app.collection_can(d.collection_id,'write') AND app.personal_assessment_eligible(d.active_version_id))
$$""",
'app.personal_assessment_view(uuid)':r"""
CREATE FUNCTION app.personal_assessment_view(p_document uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT to_jsonb(a)||jsonb_build_object('document_id',d.id,'status',d.status) FROM app.documents d JOIN app.collections c ON c.id=d.collection_id JOIN app.document_assessments a ON a.document_version_id=d.active_version_id WHERE d.id=p_document AND d.deleted_at IS NULL AND app.personal_project_owned(c.project_id)
$$""",
}

def prior(name):
 spec=importlib.util.spec_from_file_location('prior_'+name,Path(__file__).with_name(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql);op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  role='docweave_worker' if signature.startswith('app.personal_document_eligible') else 'docweave_runtime'
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {role}')
 assess=prior('0024_personal_private_knowledge').FUNCTIONS['app.assess_ingestion_version(uuid,jsonb)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
 assess=assess.replace('reviewed_by=NULL;',"reviewed_by=CASE WHEN (app.document_assessments.content_hash,app.document_assessments.parser_config_hash,app.document_assessments.rule_revision) IS NOT DISTINCT FROM (excluded.content_hash,excluded.parser_config_hash,excluded.rule_revision) THEN app.document_assessments.reviewed_by ELSE NULL END;")
 op.execute(assess)
 index=prior('0009_retrieval').FUNCTIONS['app.index_input(uuid,uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
 marker="    IF NOT app.index_source_current(d.id) OR v.configuration"
 check="    IF EXISTS(SELECT 1 FROM app.collections c WHERE c.id=d.collection_id AND app.personal_project_owned(c.project_id)) AND NOT app.personal_assessment_eligible(v.id) THEN RAISE EXCEPTION 'Assessment required' USING ERRCODE='DW020'; END IF;"
 index=index.replace(marker,check+'\n'+marker)
 op.execute(index)

def downgrade():
 for name,signature in (('0024_personal_private_knowledge','app.assess_ingestion_version(uuid,jsonb)'),('0009_retrieval','app.index_input(uuid,uuid)')):
  op.execute(prior(name).FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 for signature in reversed(FUNCTIONS):op.execute(f'DROP FUNCTION {signature}')
