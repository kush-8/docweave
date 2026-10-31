"""Deduplicated shared public-source preparation jobs and version assessments."""
from alembic import op
import sqlalchemy as sa
revision='0019_shared_ingestion'
down_revision='0018_personal_job_context'
branch_labels=None
depends_on=None
SERVICE='60000000-0000-4000-8000-000000000001'

def upgrade():
 op.execute("INSERT INTO app.users(id,issuer,subject,display_name) VALUES ('60000000-0000-4000-8000-000000000001','docweave:service','public-catalog-v1','Public documentation worker') ON CONFLICT(id) DO NOTHING")
 op.create_table('catalog_jobs',sa.Column('id',sa.UUID(),primary_key=True,server_default=sa.text('gen_random_uuid()')),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('catalog_revision_id',sa.UUID(),sa.ForeignKey('app.public_catalog_revisions.id',ondelete='RESTRICT'),nullable=False),sa.Column('generation_id',sa.UUID(),sa.ForeignKey('app.index_generations.id',ondelete='RESTRICT'),nullable=False),sa.Column('document_id',sa.UUID(),sa.ForeignKey('app.documents.id',ondelete='RESTRICT')),sa.Column('status',sa.Text(),nullable=False,server_default='queued'),sa.Column('stage',sa.Text(),nullable=False,server_default='queued'),sa.Column('lease_token',sa.UUID()),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),sa.UniqueConstraint('catalog_revision_id','generation_id',name='uq_catalog_jobs_revision_generation'),schema='app')
 op.execute('ALTER TABLE app.catalog_jobs ENABLE ROW LEVEL SECURITY')
 op.execute('REVOKE ALL ON app.catalog_jobs FROM PUBLIC,docweave_runtime,docweave_worker')
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  if signature!='app.defer_catalog_job(uuid)':
   op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')

FUNCTIONS={
'app.defer_catalog_job(uuid)':r"""
CREATE FUNCTION app.defer_catalog_job(p_id uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE queued bigint;
BEGIN
 SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.catalog',0,'public-catalog',NULL,jsonb_build_object('job_id',p_id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
END $$""",
'app.personal_catalog_definitions()':r"""
CREATE FUNCTION app.personal_catalog_definitions() RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT to_jsonb(r)||jsonb_build_object('revision_id',r.id,'eligible',true) FROM app.public_catalog_revisions r WHERE r.enabled AND r.source_approved
$$""",
'app.personal_reconcile_catalog(uuid,uuid,jsonb,uuid)':r"""
CREATE FUNCTION app.personal_reconcile_catalog(p_project uuid,p_actor uuid,p_choices jsonb,p_generation uuid) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p app.projects%ROWTYPE; item jsonb; r app.public_catalog_revisions%ROWTYPE; job uuid;
BEGIN
 SELECT * INTO p FROM app.projects WHERE id=p_project AND owner_user_id=p_actor FOR UPDATE;
 IF p.id IS NULL THEN RETURN false; END IF;
 DELETE FROM app.project_catalog_selections s WHERE s.project_id=p.id AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) d WHERE d->>'id'=s.dependency_id AND EXISTS(SELECT 1 FROM app.public_catalog_revisions cr WHERE cr.id=s.catalog_revision_id AND lower(cr.technology)=lower(d->>'technology') AND (cr.coverage->>'version'=d->>'docs_target' OR s.fallback_accepted)));
 FOR item IN SELECT * FROM jsonb_array_elements(p_choices) LOOP
  SELECT * INTO r FROM app.public_catalog_revisions WHERE id=(item->>'revision_id')::uuid AND enabled AND source_approved;
  IF r.id IS NULL OR r.coverage->>'granularity'<>'exact' OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) d WHERE d->>'id'=item->>'dependency_id' AND lower(d->>'technology')=lower(r.technology) AND d->>'docs_target'=r.coverage->>'version' AND coalesce(d->>'role','runtime')='runtime' AND coalesce((d->>'direct')::boolean,true)) THEN CONTINUE; END IF;
  INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id) VALUES(p.id,item->>'dependency_id',r.id) ON CONFLICT(project_id,dependency_id) DO UPDATE SET catalog_revision_id=excluded.catalog_revision_id,fallback_accepted=false;
  IF EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled) THEN
   job:=NULL;
   INSERT INTO app.catalog_jobs(catalog_revision_id,generation_id) VALUES(r.id,p_generation) ON CONFLICT(catalog_revision_id,generation_id) DO NOTHING RETURNING id INTO job;
   IF job IS NOT NULL THEN PERFORM app.defer_catalog_job(job); END IF;
  END IF;
 END LOOP;
 RETURN true;
END $$""",
'app.claim_catalog_job(uuid)':r"""
CREATE FUNCTION app.claim_catalog_job(p_id uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.catalog_jobs%ROWTYPE; r app.public_catalog_revisions%ROWTYPE; c uuid; selection uuid; source uuid; document uuid;
BEGIN
 SELECT * INTO j FROM app.catalog_jobs WHERE id=p_id FOR UPDATE;
 IF j.id IS NULL OR j.status NOT IN ('queued','capacity') AND NOT(j.status='running' AND j.lease_expires_at<now()) THEN RETURN NULL; END IF;
 SELECT * INTO r FROM app.public_catalog_revisions WHERE id=j.catalog_revision_id AND enabled AND source_approved FOR SHARE;
 IF r.id IS NULL OR NOT EXISTS(SELECT 1 FROM app.index_generations WHERE id=j.generation_id AND enabled) THEN UPDATE app.catalog_jobs SET status='blocked_policy',stage='Source or generation revoked' WHERE id=p_id; RETURN NULL; END IF;
 IF j.document_id IS NULL THEN
  SELECT id INTO c FROM app.collections WHERE catalog_revision_id=r.id LIMIT 1;
  IF c IS NULL THEN
   INSERT INTO app.collections(catalog_revision_id,name) VALUES(r.id,r.technology||' documentation') RETURNING id INTO c;
   INSERT INTO app.documentation_selections(catalog_revision_id,approved_by,technology,docs_target,coverage,origin,path_prefix,source_url,attribution) VALUES(r.id,'60000000-0000-4000-8000-000000000001',r.technology,r.docs_target,r.coverage,r.origin,r.path_prefix,r.source_url,r.attribution) RETURNING id INTO selection;
   INSERT INTO app.sources(collection_id,source_selection_id) VALUES(c,selection) RETURNING id INTO source;
   INSERT INTO app.documents(collection_id,source_id,title,media_type) VALUES(c,source,r.technology||' documentation','text/markdown') RETURNING id INTO document;
  ELSE
   SELECT id INTO document FROM app.documents WHERE collection_id=c AND deleted_at IS NULL LIMIT 1;
  END IF;
  UPDATE app.catalog_jobs SET document_id=document WHERE id=p_id;
 END IF;
 UPDATE app.catalog_jobs SET status='running',stage='Fetching documentation',lease_token=gen_random_uuid(),lease_expires_at=now()+interval '10 minutes' WHERE id=p_id RETURNING * INTO j;
 RETURN to_jsonb(j)||jsonb_build_object('source',to_jsonb(r));
END $$""",
'app.catalog_job_authorized(uuid,uuid)':r"""
CREATE FUNCTION app.catalog_job_authorized(p_id uuid,p_token uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.catalog_jobs j JOIN app.public_catalog_revisions r ON r.id=j.catalog_revision_id JOIN app.index_generations g ON g.id=j.generation_id WHERE j.id=p_id AND j.lease_token=p_token AND j.status='running' AND j.lease_expires_at>now() AND r.enabled AND r.source_approved AND g.enabled)
$$""",
'app.publish_catalog_snapshot(uuid,uuid,uuid,jsonb,jsonb)':r"""
CREATE FUNCTION app.publish_catalog_snapshot(p_job uuid,p_token uuid,p_version uuid,p_parsed jsonb,p_assessment jsonb) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.catalog_jobs%ROWTYPE;
BEGIN
 IF NOT app.catalog_job_authorized(p_job,p_token) THEN RETURN false; END IF;
 SELECT * INTO j FROM app.catalog_jobs WHERE id=p_job FOR UPDATE;
 IF p_assessment->>'content_hash'<>p_parsed->>'sha256' OR p_assessment->>'document_version'<>p_version::text OR p_assessment->>'rule_revision'<>'deterministic-v1' THEN RAISE EXCEPTION 'Assessment mismatch' USING ERRCODE='22023'; END IF;
 INSERT INTO app.document_versions(id,document_id,content_hash,configuration,source_url) SELECT p_version,j.document_id,p_parsed->>'sha256',p_parsed->>'configuration',r.source_url FROM app.public_catalog_revisions r WHERE r.id=j.catalog_revision_id;
 INSERT INTO app.document_assessments(document_version_id,content_hash,parser_config_hash,rule_revision,credential_blocked,injection_flagged,complete) VALUES(p_version,p_assessment->>'content_hash',p_assessment->>'parser_config_hash',p_assessment->>'rule_revision',(p_assessment->>'credential_blocked')::boolean,(p_assessment->>'injection_flagged')::boolean,(p_assessment->>'complete')::boolean);
 UPDATE app.documents SET active_version_id=p_version,status=CASE WHEN app.personal_assessment_eligible(p_version) THEN 'prepared' ELSE 'quarantined' END,media_type=CASE WHEN p_parsed->>'configuration' LIKE '%text/markdown' THEN 'text/markdown' ELSE 'text/plain' END WHERE id=j.document_id;
 UPDATE app.catalog_jobs SET status=CASE WHEN app.personal_assessment_eligible(p_version) THEN 'running' ELSE 'pending_review' END,stage=CASE WHEN app.personal_assessment_eligible(p_version) THEN 'Building documentation index' ELSE 'Document quarantined' END WHERE id=p_job;
 RETURN true;
END $$""",
'app.finish_catalog_job(uuid,uuid,text)':r"""
CREATE FUNCTION app.finish_catalog_job(p_job uuid,p_token uuid,p_status text) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF p_status NOT IN ('completed','failed','capacity','pending_review','blocked_policy') THEN RAISE EXCEPTION 'Invalid job status' USING ERRCODE='22023'; END IF;
 UPDATE app.catalog_jobs SET status=p_status,stage=CASE p_status WHEN 'completed' THEN 'Documentation ready' WHEN 'capacity' THEN 'Waiting for an approved embedding profile' ELSE p_status END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job AND lease_token=p_token AND status='running';
 RETURN FOUND;
END $$""",
}

def downgrade():
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
 op.drop_table('catalog_jobs',schema='app')
 # The service identity may own retained audit/ledger records; preserve it.
