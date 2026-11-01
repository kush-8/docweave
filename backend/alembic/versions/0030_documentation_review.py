"""Project-scoped version decisions and operator-owned public source coverage."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import importlib.util
from pathlib import Path

revision = '0030_documentation_review'
down_revision = '0029_sync_publication'
branch_labels = None
depends_on = None


FUNCTIONS = {
'app.catalog_dependency_matches(uuid,jsonb)': r"""
CREATE FUNCTION app.catalog_dependency_matches(p_revision uuid,p_dependency jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.public_catalog_revisions r WHERE r.id=p_revision
 AND coalesce(p_dependency->>'ecosystem',r.ecosystem)=r.ecosystem
 AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(r.package_aliases||jsonb_build_array(r.technology)) alias(name)
 WHERE CASE WHEN r.ecosystem='python' THEN regexp_replace(lower(alias.name),'[-_.]+','-','g') ELSE lower(alias.name) END
 =CASE WHEN r.ecosystem='python' THEN regexp_replace(lower(p_dependency->>'technology'),'[-_.]+','-','g') ELSE lower(p_dependency->>'technology') END)
 AND (r.coverage->>'granularity'='exact' AND p_dependency->>'docs_target'=r.coverage->>'version'
 OR p_dependency->>'docs_target' ~ '^[0-9]+(\.[0-9]+){0,3}([-+][A-Za-z0-9.-]+)?$' AND (
 r.coverage->>'granularity'='major' AND r.coverage->>'version' ~ '^[0-9]+$' AND split_part(p_dependency->>'docs_target','.',1)=r.coverage->>'version'
 OR r.coverage->>'granularity'='minor' AND r.coverage->>'version' ~ '^[0-9]+\.[0-9]+$' AND split_part(p_dependency->>'docs_target','.',1)||'.'||split_part(p_dependency->>'docs_target','.',2)=r.coverage->>'version')))
$$""",
'app.catalog_revision_ready(uuid,uuid)': r"""
CREATE FUNCTION app.catalog_revision_ready(p_revision uuid,p_generation uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id
 JOIN app.document_indexes i ON i.document_id=d.id JOIN app.index_generations g ON g.id=i.generation_id
 LEFT JOIN app.sources s ON s.id=d.source_id LEFT JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
 WHERE c.catalog_revision_id=p_revision AND g.id=p_generation AND g.enabled AND d.deleted_at IS NULL
 AND app.personal_assessment_eligible(i.document_version_id)
 AND (d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active AND ds.catalog_revision_id=p_revision))
$$""",
'app.catalog_entries(uuid)': r"""
CREATE FUNCTION app.catalog_entries(p_generation uuid) RETURNS SETOF jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT to_jsonb(r)||jsonb_build_object('revision_id',r.id,'eligible',true,'generation_id',p_generation,
 'indexed_generation_id',CASE WHEN r.source_approved AND app.catalog_revision_ready(r.id,p_generation) THEN p_generation ELSE NULL END,
 'status',CASE WHEN NOT r.source_approved THEN 'pending_review'
 WHEN app.catalog_revision_ready(r.id,p_generation) THEN 'indexed'
 WHEN NOT EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) THEN 'capacity'
 WHEN j.status IN ('queued','running') THEN 'processing'
 WHEN j.status='blocked_policy' THEN 'pending_review'
 WHEN j.status IN ('failed','capacity','pending_review') THEN j.status ELSE 'missing' END,
 'active_job',r.source_approved AND coalesce(j.status IN ('queued','running'),false)
 AND EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled),
 'progress',CASE WHEN r.source_approved THEN j.stage ELSE 'Operator source approval required' END)
 FROM app.public_catalog_revisions r LEFT JOIN app.catalog_jobs j ON j.catalog_revision_id=r.id AND j.generation_id=p_generation
 WHERE r.enabled ORDER BY r.technology,r.id
$$""",
'app.personal_catalog_state(uuid,uuid,uuid)': r"""
CREATE OR REPLACE FUNCTION app.personal_catalog_state(p_job uuid,p_token uuid,p_generation uuid) RETURNS SETOF jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF app.personal_job_context(p_job,p_token) IS NULL THEN RETURN; END IF;
 RETURN QUERY SELECT app.catalog_entries(p_generation);
END $$""",
'app.catalog_selection_current(uuid,uuid)': r"""
CREATE FUNCTION app.catalog_selection_current(p_project uuid,p_revision uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.project_catalog_selections s JOIN app.public_catalog_revisions r ON r.id=s.catalog_revision_id
 JOIN app.projects p ON p.id=s.project_id,jsonb_array_elements(p.stack) d
 WHERE s.catalog_revision_id=p_revision AND s.project_id=p_project
 AND app.personal_project_owned(s.project_id) AND s.active AND r.enabled AND r.source_approved AND d->>'id'=s.dependency_id
 AND app.catalog_dependency_matches(r.id,d) AND (r.coverage->>'granularity'='exact'
 OR s.fallback_accepted AND s.accepted_docs_target=d->>'docs_target'))
$$""",
'app.personal_collection_allowed(uuid)': r"""
CREATE OR REPLACE FUNCTION app.personal_collection_allowed(p_collection uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.collections c WHERE c.id=p_collection AND (
 c.project_id=nullif(current_setting('docweave.personal_project_id',true),'')::uuid AND app.personal_project_owned(c.project_id)
 OR c.catalog_revision_id IS NOT NULL AND app.catalog_selection_current(nullif(current_setting('docweave.personal_project_id',true),'')::uuid,c.catalog_revision_id)))
$$""",
'app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)': r"""
CREATE FUNCTION app.personal_choose_documentation(p_project uuid,p_dependency text,p_expected integer,p_revision uuid,p_fallback boolean,p_generation uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p app.projects%ROWTYPE; r app.public_catalog_revisions%ROWTYPE; d jsonb; changed integer;
BEGIN
 IF NOT app.personal_project_owned(p_project) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended(p_project::text,730004)) THEN RAISE EXCEPTION 'Context busy' USING ERRCODE='40001'; END IF;
 SELECT * INTO p FROM app.projects WHERE id=p_project AND app.personal_project_owned(id) FOR UPDATE;
 IF p.context_revision<>p_expected THEN RAISE EXCEPTION 'Context changed' USING ERRCODE='40001'; END IF;
 SELECT item INTO d FROM jsonb_array_elements(p.stack) item WHERE item->>'id'=p_dependency;
 IF d IS NULL THEN RAISE EXCEPTION 'Unknown dependency' USING ERRCODE='22023'; END IF;
 IF p_revision IS NULL THEN
  UPDATE app.project_catalog_selections SET active=false WHERE project_id=p.id AND dependency_id=p_dependency AND active;
 ELSE
  SELECT * INTO r FROM app.public_catalog_revisions WHERE id=p_revision AND enabled AND source_approved FOR SHARE;
  IF r.id IS NULL OR NOT app.catalog_dependency_matches(r.id,d) OR r.coverage->>'granularity'<>'exact' AND NOT p_fallback THEN
   RAISE EXCEPTION 'Source or version requires approval' USING ERRCODE='22023'; END IF;
  INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id,fallback_accepted,accepted_docs_target,active)
  VALUES(p.id,p_dependency,r.id,r.coverage->>'granularity'<>'exact',d->>'docs_target',true)
  ON CONFLICT(project_id,dependency_id) DO UPDATE SET catalog_revision_id=excluded.catalog_revision_id,
   fallback_accepted=excluded.fallback_accepted,accepted_docs_target=excluded.accepted_docs_target,active=true
  WHERE (project_catalog_selections.catalog_revision_id,project_catalog_selections.fallback_accepted,project_catalog_selections.accepted_docs_target,project_catalog_selections.active)
   IS DISTINCT FROM (excluded.catalog_revision_id,excluded.fallback_accepted,excluded.accepted_docs_target,true);
 END IF;
 GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed>0 THEN UPDATE app.projects SET context_revision=context_revision+1 WHERE id=p.id; END IF;
 PERFORM app.personal_reconcile_catalog(p.id,p.owner_user_id,'[]'::jsonb,p_generation);
 RETURN true;
END $$""",
'app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)': r"""
CREATE OR REPLACE FUNCTION app.personal_reconcile_catalog(p_project uuid,p_actor uuid,p_choices jsonb,p_generation uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p app.projects%ROWTYPE; item jsonb; r app.public_catalog_revisions%ROWTYPE; job uuid; selected record;
BEGIN
 SELECT * INTO p FROM app.projects WHERE id=p_project AND owner_user_id=p_actor FOR UPDATE;
 IF p.id IS NULL THEN RETURN false; END IF;
 DELETE FROM app.project_catalog_selections s WHERE s.project_id=p.id AND NOT EXISTS(
 SELECT 1 FROM jsonb_array_elements(p.stack) d JOIN app.public_catalog_revisions cr ON cr.id=s.catalog_revision_id
 WHERE d->>'id'=s.dependency_id AND cr.enabled AND cr.source_approved AND app.catalog_dependency_matches(cr.id,d)
 AND (cr.coverage->>'granularity'='exact' OR s.fallback_accepted AND s.accepted_docs_target=d->>'docs_target'));
 FOR item IN SELECT * FROM jsonb_array_elements(p_choices) LOOP
  SELECT * INTO r FROM app.public_catalog_revisions WHERE id=(item->>'revision_id')::uuid AND enabled AND source_approved;
  IF r.id IS NULL OR r.coverage->>'granularity'<>'exact' OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) d
  WHERE d->>'id'=item->>'dependency_id' AND app.catalog_dependency_matches(r.id,d)
  AND coalesce(d->>'role','runtime')='runtime' AND coalesce((d->>'direct')::boolean,true)) THEN CONTINUE; END IF;
  INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id)
  VALUES(p.id,item->>'dependency_id',r.id) ON CONFLICT(project_id,dependency_id) DO NOTHING;
 END LOOP;
 FOR selected IN SELECT s.catalog_revision_id FROM app.project_catalog_selections s WHERE s.project_id=p.id AND s.active LOOP
  IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled)
   AND NOT app.catalog_revision_ready(selected.catalog_revision_id,p_generation) THEN
   job:=NULL;
   INSERT INTO app.catalog_jobs(catalog_revision_id,generation_id) VALUES(selected.catalog_revision_id,p_generation)
   ON CONFLICT(catalog_revision_id,generation_id) DO NOTHING RETURNING id INTO job;
   IF job IS NOT NULL THEN PERFORM app.defer_catalog_job(job); END IF;
  END IF;
 END LOOP;
 RETURN true;
END $$""",
'app.personal_select_catalog(uuid,uuid,jsonb)': r"""
CREATE OR REPLACE FUNCTION app.personal_select_catalog(p_job uuid,p_token uuid,p_choices jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE context jsonb;
BEGIN
 context:=app.personal_job_context(p_job,p_token);
 IF context IS NULL THEN RETURN false; END IF;
 IF jsonb_typeof(p_choices)<>'array' OR jsonb_array_length(p_choices)>10000 THEN RAISE EXCEPTION 'Invalid selection' USING ERRCODE='22023'; END IF;
 RETURN app.personal_reconcile_catalog((context->'project'->>'id')::uuid,
 nullif(current_setting('docweave.actor_id',true),'')::uuid,p_choices,NULL);
END $$""",
}


def prior(name):
    spec = importlib.util.spec_from_file_location('review_prior_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade():
    op.add_column('public_catalog_revisions', sa.Column('package_aliases', JSONB(), nullable=False, server_default='[]'), schema='app')
    op.create_check_constraint(op.f('ck_public_catalog_revisions_aliases_array'), 'public_catalog_revisions', "jsonb_typeof(package_aliases)='array'", schema='app')
    op.add_column('project_catalog_selections', sa.Column('accepted_docs_target', sa.Text()), schema='app')
    op.add_column('project_catalog_selections', sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')), schema='app')
    for signature, sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
        if signature.startswith(('app.catalog_entries', 'app.personal_collection_allowed')):
            roles = 'docweave_runtime,docweave_worker'
        elif signature.startswith('app.personal_choose_documentation'):
            roles = 'docweave_runtime'
        elif signature.startswith(('app.personal_catalog_state', 'app.personal_select_catalog', 'app.personal_reconcile_catalog')):
            roles = 'docweave_worker'
        else:
            continue
        op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {roles}')
    project = prior('0015_personal_projects').FUNCTIONS['app.personal_project(uuid)']
    project = project.replace('WHERE s.project_id=p.id) THEN', 'WHERE s.project_id=p.id AND s.active) THEN')
    project = project.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1).replace("'context_revision',p.context_revision,", """'catalog_selections',coalesce((SELECT jsonb_agg(jsonb_build_object('dependency_id',s.dependency_id,'revision_id',s.catalog_revision_id,
 'fallback_accepted',s.fallback_accepted,'accepted_docs_target',s.accepted_docs_target)) FROM app.project_catalog_selections s WHERE s.project_id=p.id AND s.active),'[]'::jsonb),
 'excluded_documentation',coalesce((SELECT jsonb_agg(s.dependency_id) FROM app.project_catalog_selections s WHERE s.project_id=p.id AND NOT s.active),'[]'::jsonb),
 'context_revision',p.context_revision,""")
    op.execute(project)
    citations = prior('0022_personal_release').FUNCTIONS['app.personal_citations_current(uuid,jsonb)']
    citations = citations.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1).replace(
        'c.catalog_revision_id IS NOT NULL AND r.enabled',
        'c.catalog_revision_id IS NOT NULL AND app.catalog_selection_current(p_project,c.catalog_revision_id) AND r.enabled').replace(
        'AND d.deleted_at IS NULL AND app.personal_assessment_eligible',
        'AND EXISTS(SELECT 1 FROM app.index_generations g WHERE g.id=ch.generation_id AND g.enabled) AND d.deleted_at IS NULL AND app.personal_assessment_eligible')
    op.execute(citations)


def downgrade():
    for name, signature in (
        ('0015_personal_projects', 'app.personal_project(uuid)'),
        ('0018_personal_job_context', 'app.personal_select_catalog(uuid,uuid,jsonb)'),
        ('0017_personal_retrieval', 'app.personal_collection_allowed(uuid)'),
        ('0020_catalog_publication', 'app.personal_catalog_state(uuid,uuid,uuid)'),
        ('0022_personal_release', 'app.personal_citations_current(uuid,jsonb)'),
    ):
        op.execute(prior(name).FUNCTIONS[signature].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1).replace('CREATE OR REPLACE OR REPLACE', 'CREATE OR REPLACE'))
    reconcile = prior('0019_shared_ingestion').FUNCTIONS['app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)'].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
    reconcile = reconcile.replace("IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) THEN", "IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) AND NOT EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id)) THEN")
    op.execute(reconcile)
    for signature in ('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)', 'app.catalog_entries(uuid)', 'app.catalog_revision_ready(uuid,uuid)', 'app.catalog_selection_current(uuid,uuid)', 'app.catalog_dependency_matches(uuid,jsonb)'):
        op.execute(f'DROP FUNCTION {signature}')
    op.drop_column('project_catalog_selections', 'accepted_docs_target', schema='app')
    op.drop_column('project_catalog_selections', 'active', schema='app')
    op.drop_constraint(op.f('ck_public_catalog_revisions_aliases_array'), 'public_catalog_revisions', schema='app', type_='check')
    op.drop_column('public_catalog_revisions', 'package_aliases', schema='app')
