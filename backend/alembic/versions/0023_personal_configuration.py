"""Safe configuration views, lease renewal and catalog reuse checks."""
from alembic import op
import importlib.util
from pathlib import Path
revision='0023_personal_configuration'
down_revision='0022_personal_release'
branch_labels=None
depends_on=None
FUNCTIONS={
'app.personal_embedding_matches(uuid,uuid)':r"""
CREATE FUNCTION app.personal_embedding_matches(p_generation uuid,p_profile uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.index_generations g JOIN app.provider_profiles p ON p.id=p_profile WHERE g.id=p_generation AND g.enabled AND p.role='embedding' AND p.model=g.model AND p.backend=g.backend AND p.processor_ids @> g.processor_ids AND g.processor_ids @> p.processor_ids AND app.profile_disabled_reason(p.id) IS NULL)
$$""",
'app.personal_required_processors()':r"""
CREATE FUNCTION app.personal_required_processors() RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',p.id,'provider',p.provider,'roles',p.roles,'backend',p.backend)
 FROM app.processors p WHERE p.enabled AND EXISTS(SELECT 1 FROM app.provider_profiles profile WHERE profile.processor_ids ? p.id AND app.profile_disabled_reason(profile.id) IS NULL)
 ORDER BY p.id
$$""",
'app.personal_profile(uuid)':r"""
CREATE OR REPLACE FUNCTION app.personal_profile(p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',p.id,'model',p.model,'backend',p.backend,'provider',p.provider,'role',p.role,'processor_ids',p.processor_ids,'available',app.profile_disabled_reason(p.id) IS NULL) FROM app.provider_profiles p WHERE p.id=p_id
$$""",
}

def prior(name):
 spec=importlib.util.spec_from_file_location('prior_'+name,Path(__file__).with_name(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  role='docweave_runtime' if signature.startswith('app.personal_required_processors') else 'docweave_worker'
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {role}')
 reconcile=prior('0019_shared_ingestion').FUNCTIONS['app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
 reconcile=reconcile.replace("IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) THEN", "IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) AND NOT EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id)) THEN")
 op.execute(reconcile)
 claim=prior('0019_shared_ingestion').FUNCTIONS['app.claim_catalog_job(uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace('source_approved FOR SHARE','source_approved FOR UPDATE')
 op.execute(claim)

def downgrade():
 for name,signature in (('0019_shared_ingestion','app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)'),('0019_shared_ingestion','app.claim_catalog_job(uuid)'),('0022_personal_release','app.personal_profile(uuid)')):
  op.execute(prior(name).FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 for signature in ('app.personal_required_processors()','app.personal_embedding_matches(uuid,uuid)'):op.execute(f'DROP FUNCTION {signature}')
