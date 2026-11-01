"""Preserve owner exclusions and the fetched source MIME through isolated parsing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0035_source_media'
down_revision='0034_private_source_review'
branch_labels=None
depends_on=None

MEDIA=r"""
CREATE FUNCTION app.ingestion_source_media(p_job uuid,p_token uuid,p_media text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.ingestion_jobs%ROWTYPE;
BEGIN
 IF p_media NOT IN ('text/plain','text/markdown','text/html') OR NOT app.ingestion_authorized(p_job,p_token) THEN RETURN false; END IF;
 SELECT jobs.* INTO j FROM app.ingestion_jobs jobs JOIN app.documents d ON d.id=jobs.document_id
 WHERE jobs.id=p_job AND jobs.status='running' AND jobs.lease_token=p_token AND d.source_id IS NOT NULL FOR UPDATE OF jobs;
 IF j.id IS NULL THEN RETURN false; END IF;
 UPDATE app.ingestion_jobs SET media_type=p_media,configuration=regexp_replace(configuration,':text/(plain|markdown|html)$',':'||p_media) WHERE id=j.id;
 UPDATE app.documents SET media_type=p_media WHERE id=j.document_id;
 RETURN true;
END $$
"""
EXCLUDED=r"""
CREATE FUNCTION app.documentation_excluded(p_project uuid,p_dependency jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.documentation_exclusions) item
 WHERE p.id=p_project AND item->>'dependency_id'=p_dependency->>'id' AND item->>'docs_target'=p_dependency->>'docs_target')
$$
"""
PRIVATE_UPDATE="UPDATE app.documentation_selections SET active=false WHERE project_id=p.id AND approved_stack->>'id'=p_dependency AND active;"
EXCLUSION_UPDATE=PRIVATE_UPDATE+r"""
 GET DIAGNOSTICS private_changed=ROW_COUNT;
 UPDATE app.projects SET documentation_exclusions=
  coalesce((SELECT jsonb_agg(item) FROM jsonb_array_elements(documentation_exclusions) item WHERE item->>'dependency_id'<>p_dependency),'[]'::jsonb)
  || CASE WHEN p_revision IS NULL THEN jsonb_build_array(jsonb_build_object('dependency_id',p_dependency,'docs_target',d->>'docs_target')) ELSE '[]'::jsonb END
 WHERE id=p.id AND (p_revision IS NULL AND NOT app.documentation_excluded(p.id,d)
 OR p_revision IS NOT NULL AND EXISTS(SELECT 1 FROM jsonb_array_elements(documentation_exclusions) item WHERE item->>'dependency_id'=p_dependency));
 GET DIAGNOSTICS exclusion_changed=ROW_COUNT;
"""
PROJECT_EXCLUDED="'excluded_documentation',coalesce("
PROJECT_EXCLUDED_AFTER="""'excluded_documentation',coalesce((SELECT jsonb_agg(item->>'dependency_id') FROM jsonb_array_elements(p.documentation_exclusions) item
 WHERE EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) dep WHERE item->>'dependency_id'=dep->>'id' AND item->>'docs_target'=dep->>'docs_target')),'[]'::jsonb)||coalesce("""
REVIEW_UPDATE='UPDATE app.projects SET context_revision=context_revision+1 WHERE id=p.id;'
REVIEW_UPDATE_AFTER="""UPDATE app.projects SET context_revision=context_revision+1,documentation_exclusions=coalesce((SELECT jsonb_agg(item) FROM jsonb_array_elements(documentation_exclusions) item WHERE item->>'dependency_id'<>p_dependency),'[]'::jsonb) WHERE id=p.id;"""
CHANGES=(
 ('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)','changed integer;','changed integer; private_changed integer; exclusion_changed integer;'),
 ('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)',PRIVATE_UPDATE,EXCLUSION_UPDATE),
 ('app.personal_choose_documentation(uuid,text,integer,uuid,boolean,uuid)','IF changed>0 THEN','IF changed>0 OR private_changed>0 OR exclusion_changed>0 THEN'),
 ('app.personal_project(uuid)',PROJECT_EXCLUDED,PROJECT_EXCLUDED_AFTER),
 ('app.personal_review_source(uuid,text,integer,jsonb)',REVIEW_UPDATE,REVIEW_UPDATE_AFTER),
 ('app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)',"AND coalesce(d->>'role','runtime')='runtime'","AND NOT app.documentation_excluded(p.id,d) AND coalesce(d->>'role','runtime')='runtime'"),
 ('app.catalog_selection_current(uuid,uuid)',"AND d->>'id'=s.dependency_id","AND d->>'id'=s.dependency_id AND NOT app.documentation_excluded(p_project,d)"),
 ('app.publish_catalog_snapshot(uuid,uuid,uuid,jsonb,jsonb)',"media_type=CASE WHEN p_parsed->>'configuration' LIKE '%text/markdown'", "media_type=CASE WHEN p_parsed->>'configuration' LIKE '%text/html' THEN 'text/html' WHEN p_parsed->>'configuration' LIKE '%text/markdown'"),
)


def replace(signature,before,after):
    definition=op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'),{'signature':signature})
    if before not in definition:
        raise ValueError('Unexpected source admission function definition: '+signature)
    op.execute(definition.replace(before,after))


def upgrade():
    op.add_column('projects',sa.Column('documentation_exclusions',JSONB(),nullable=False,server_default='[]'),schema='app')
    op.create_check_constraint(op.f('ck_projects_documentation_exclusions_array'),'projects',"jsonb_typeof(documentation_exclusions)='array'",schema='app')
    op.execute(MEDIA)
    op.execute(EXCLUDED)
    op.execute('REVOKE ALL ON FUNCTION app.ingestion_source_media(uuid,uuid,text),app.documentation_excluded(uuid,jsonb) FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('GRANT EXECUTE ON FUNCTION app.ingestion_source_media(uuid,uuid,text) TO docweave_worker')
    for signature,before,after in CHANGES:
        replace(signature,before,after)


def downgrade():
    for signature,before,after in reversed(CHANGES):
        replace(signature,after,before)
    op.execute('DROP FUNCTION app.ingestion_source_media(uuid,uuid,text),app.documentation_excluded(uuid,jsonb)')
    op.drop_constraint(op.f('ck_projects_documentation_exclusions_array'),'projects',schema='app',type_='check')
    op.drop_column('projects','documentation_exclusions',schema='app')
