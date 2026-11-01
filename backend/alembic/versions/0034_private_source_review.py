"""Owner-reviewed publisher sources remain private and bind exact stack facts."""
from alembic import op
import sqlalchemy as sa

revision='0034_private_source_review'
down_revision='0033_recovery_release'
branch_labels=None
depends_on=None

REVIEW=r"""
CREATE FUNCTION app.personal_review_source(p_project uuid,p_dependency text,p_expected integer,p_values jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p app.projects%ROWTYPE; d jsonb; selection uuid; collection uuid; coverage jsonb:=p_values->'coverage'; target text;
BEGIN
 IF NOT app.personal_project_owned(p_project) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended(p_project::text,730004)) THEN RAISE EXCEPTION 'Context busy' USING ERRCODE='40001'; END IF;
 SELECT * INTO p FROM app.projects WHERE id=p_project AND app.personal_project_owned(id) FOR UPDATE;
 IF p.context_revision<>p_expected THEN RAISE EXCEPTION 'Context changed' USING ERRCODE='40001'; END IF;
 SELECT item INTO d FROM jsonb_array_elements(p.stack) item WHERE item->>'id'=p_dependency;
 target:=d->>'docs_target';
 IF d IS NULL OR target IS NULL OR p_values->>'docs_target' IS DISTINCT FROM target
 OR p_values->>'technology' IS DISTINCT FROM d->>'technology'
 OR coalesce(p_values->>'source_url','') NOT LIKE 'https://%'
 OR coalesce(p_values->>'origin','') NOT LIKE 'https://%'
 OR coalesce(p_values->>'path_prefix','') NOT LIKE '/%'
 OR NOT (left(p_values->>'source_url',length(p_values->>'origin')+length(p_values->>'path_prefix'))=(p_values->>'origin')||(p_values->>'path_prefix')
 OR p_values->>'path_prefix'='/' AND p_values->>'source_url'=p_values->>'origin')
 OR coalesce(p_values->>'attribution','') !~ '[^[:space:]]'
 OR coverage->>'granularity'<>'exact' AND coalesce(p_values->'accept_fallback','false'::jsonb)<>'true'::jsonb
 OR NOT coalesce((coverage->>'granularity'='exact' AND coverage->>'version'=target)
 OR (target ~ '^[0-9]+(\.[0-9]+){0,3}([-+][A-Za-z0-9.-]+)?$' AND (
 coverage->>'granularity'='major' AND coverage->>'version' ~ '^[0-9]+$' AND split_part(target,'.',1)=coverage->>'version'
 OR coverage->>'granularity'='minor' AND coverage->>'version' ~ '^[0-9]+\.[0-9]+$' AND split_part(target,'.',1)||'.'||split_part(target,'.',2)=coverage->>'version')),false)
 THEN RAISE EXCEPTION 'Invalid private source review' USING ERRCODE='22023'; END IF;
 SELECT id INTO collection FROM app.collections WHERE project_id=p.id AND is_default;
 IF collection IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 UPDATE app.documentation_selections SET active=false WHERE project_id=p.id AND approved_stack->>'id'=p_dependency AND active;
 UPDATE app.project_catalog_selections SET active=false WHERE project_id=p.id AND dependency_id=p_dependency AND active;
 INSERT INTO app.documentation_selections(workspace_id,project_id,approved_by,technology,docs_target,coverage,source_url,origin,path_prefix,attribution,approved_stack)
 VALUES(p.workspace_id,p.id,p.owner_user_id,d->>'technology',target,coverage,p_values->>'source_url',p_values->>'origin',p_values->>'path_prefix',p_values->>'attribution',d) RETURNING id INTO selection;
 UPDATE app.projects SET context_revision=context_revision+1 WHERE id=p.id;
 RETURN jsonb_build_object('selection_id',selection,'collection_id',collection);
END $$
"""

ENTRIES=r"""
CREATE FUNCTION app.personal_private_source_entries(p_project uuid,p_generation uuid) RETURNS SETOF jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF NOT app.personal_project_owned(p_project) THEN RETURN; END IF;
 PERFORM set_config('docweave.personal_project_id',p_project::text,true);
 RETURN QUERY SELECT jsonb_build_object('revision_id',ds.id,'technology',ds.technology,'ecosystem',dep->>'ecosystem',
 'docs_target',ds.docs_target,'coverage',ds.coverage,'source_url',ds.source_url,'origin',ds.origin,'path_prefix',ds.path_prefix,
 'attribution',ds.attribution,'source_approved',true,'eligible',true,'package_aliases','[]'::jsonb,
 'private_selection',true,'dependency_id',dep->>'id','accepted_docs_target',dep->>'docs_target',
 'generation_id',p_generation,'indexed_generation_id',CASE WHEN ready.value THEN p_generation ELSE NULL END,
 'status',CASE WHEN ready.value THEN 'indexed'
 WHEN d.active_version_id IS NOT NULL AND NOT app.personal_assessment_eligible(d.active_version_id) THEN 'pending_review'
 WHEN j.status IN ('failed','cancelled') THEN 'failed'
 WHEN j.status IN ('queued','running') THEN 'processing'
 WHEN NOT EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) THEN 'capacity'
 WHEN NOT app.personal_index_policy(c.id,p_generation) THEN 'consent_required'
 WHEN d.active_version_id IS NOT NULL THEN 'capacity' ELSE 'missing' END,
 'active_job',coalesce(j.status IN ('queued','running'),false),'progress',j.stage)
 FROM app.documentation_selections ds JOIN app.projects p ON p.id=ds.project_id
 JOIN app.collections c ON c.project_id=p.id AND c.is_default
 CROSS JOIN LATERAL jsonb_array_elements(p.stack) dep
 LEFT JOIN app.sources s ON s.source_selection_id=ds.id AND s.deleted_at IS NULL
 LEFT JOIN app.documents d ON d.source_id=s.id AND d.deleted_at IS NULL
 LEFT JOIN LATERAL(SELECT jobs.status,jobs.stage FROM app.ingestion_jobs jobs WHERE jobs.document_id=d.id ORDER BY jobs.created_at DESC,jobs.id DESC LIMIT 1) j ON true
 CROSS JOIN LATERAL(SELECT EXISTS(SELECT 1 FROM app.document_indexes i WHERE i.document_id=d.id AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id) AND app.personal_index_policy(c.id,p_generation)) value) ready
 WHERE p.id=p_project AND ds.active AND ds.approved_stack=dep;
END $$
"""


def replace(signature,before,after):
    definition=op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'),{'signature':signature})
    if before not in definition:
        raise ValueError('Unexpected source review function definition')
    op.execute(definition.replace(before,after))


def upgrade():
    op.execute(REVIEW)
    op.execute(ENTRIES)
    for signature in ('app.personal_review_source(uuid,text,integer,jsonb)','app.personal_private_source_entries(uuid,uuid)'):
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_private_source_entries(uuid,uuid) TO docweave_worker')
    replace('app.personal_catalog_state(uuid,uuid,uuid)', 'RETURN QUERY SELECT app.catalog_entries(p_generation);',
        "RETURN QUERY SELECT app.catalog_entries(p_generation); RETURN QUERY SELECT app.personal_private_source_entries((SELECT c.project_id FROM app.personal_jobs j JOIN app.conversations c ON c.id=j.conversation_id WHERE j.id=p_job),p_generation);")
    replace('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)', 'IF p_revision IS NULL THEN',
        "UPDATE app.documentation_selections SET active=false WHERE project_id=p.id AND approved_stack->>'id'=p_dependency AND active; IF p_revision IS NULL THEN")
    replace('app.personal_citations_current(uuid,jsonb)', "c.project_id=p_project AND(d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active)",
        "c.project_id=p_project AND(d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active AND EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.stack) dep WHERE p.id=p_project AND dep=ds.approved_stack))")
    replace('app.ingestion_authorized(uuid,uuid)', 'WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active',
        'WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active AND EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.stack) dep WHERE p.id=ds.project_id AND dep=ds.approved_stack)')


def downgrade():
    replace('app.ingestion_authorized(uuid,uuid)',
        'WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active AND EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.stack) dep WHERE p.id=ds.project_id AND dep=ds.approved_stack)',
        'WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active')
    replace('app.personal_citations_current(uuid,jsonb)',
        "c.project_id=p_project AND(d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active AND EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.stack) dep WHERE p.id=p_project AND dep=ds.approved_stack))",
        "c.project_id=p_project AND(d.source_id IS NULL OR s.deleted_at IS NULL AND ds.active)")
    replace('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)',
        "UPDATE app.documentation_selections SET active=false WHERE project_id=p.id AND approved_stack->>'id'=p_dependency AND active; IF p_revision IS NULL THEN",'IF p_revision IS NULL THEN')
    replace('app.personal_catalog_state(uuid,uuid,uuid)',
        "RETURN QUERY SELECT app.catalog_entries(p_generation); RETURN QUERY SELECT app.personal_private_source_entries((SELECT c.project_id FROM app.personal_jobs j JOIN app.conversations c ON c.id=j.conversation_id WHERE j.id=p_job),p_generation);",
        'RETURN QUERY SELECT app.catalog_entries(p_generation);')
    op.execute('DROP FUNCTION app.personal_private_source_entries(uuid,uuid),app.personal_review_source(uuid,text,integer,jsonb)')
