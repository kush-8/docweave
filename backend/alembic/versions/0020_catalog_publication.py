"""Publish shared indexes atomically and wake durable source-dependent turns."""
from alembic import op
revision='0020_catalog_publication'
down_revision='0019_shared_ingestion'
branch_labels=None
depends_on=None
FUNCTIONS={
'app.catalog_index_input(uuid,uuid)':r"""
CREATE FUNCTION app.catalog_index_input(p_job uuid,p_token uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.catalog_jobs%ROWTYPE; d app.documents%ROWTYPE; v app.document_versions%ROWTYPE; g app.index_generations%ROWTYPE;
BEGIN
 IF NOT app.catalog_job_authorized(p_job,p_token) THEN RAISE EXCEPTION 'Source revoked' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM app.catalog_jobs WHERE id=p_job;
 SELECT * INTO d FROM app.documents WHERE id=j.document_id AND deleted_at IS NULL;
 SELECT * INTO v FROM app.document_versions WHERE id=d.active_version_id;
 SELECT * INTO g FROM app.index_generations WHERE id=j.generation_id AND enabled;
 IF v.id IS NULL THEN RETURN jsonb_build_object('document_id',d.id,'version_id',NULL); END IF;
 IF NOT app.personal_assessment_eligible(v.id) OR v.configuration<>g.chunker||':'||d.media_type THEN RAISE EXCEPTION 'Document requires assessment' USING ERRCODE='DW020'; END IF;
 RETURN jsonb_build_object('document_id',d.id,'version_id',v.id,'content_hash',v.content_hash,'configuration',v.configuration,'generation_id',g.id,'collection_id',d.collection_id,'existing_chunks',(SELECT count(*) FROM app.chunks WHERE document_version_id=v.id AND generation_id=g.id));
END $$""",
'app.catalog_snapshot(uuid,uuid)':r"""
CREATE FUNCTION app.catalog_snapshot(p_job uuid,p_token uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('version_id',v.id,'content_hash',v.content_hash,'configuration',v.configuration,'eligible',app.personal_assessment_eligible(v.id))
 FROM app.catalog_jobs j JOIN app.documents d ON d.id=j.document_id JOIN app.document_versions v ON v.id=d.active_version_id WHERE j.id=p_job AND app.catalog_job_authorized(p_job,p_token)
$$""",
'app.catalog_insert_chunks(uuid,uuid,jsonb)':r"""
CREATE FUNCTION app.catalog_insert_chunks(p_job uuid,p_token uuid,p_chunks jsonb) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,public AS $$
DECLARE snapshot jsonb; added integer;
BEGIN
 snapshot:=app.catalog_index_input(p_job,p_token);
 IF snapshot->>'version_id' IS NULL OR jsonb_typeof(p_chunks)<>'array' OR jsonb_array_length(p_chunks) NOT BETWEEN 1 AND 64 THEN RAISE EXCEPTION 'Invalid publication' USING ERRCODE='22023'; END IF;
 INSERT INTO app.chunks(collection_id,document_id,document_version_id,generation_id,start_offset,end_offset,heading,line_start,line_end,content,terms,token_count,embedding,source_url,captured_at,provenance)
 SELECT d.collection_id,d.id,v.id,j.generation_id,(item->>'start')::integer,(item->>'end')::integer,item->>'heading',(item->>'line_start')::integer,(item->>'line_end')::integer,item->>'content',tokens,(SELECT coalesce(sum(value::integer),0) FROM jsonb_each_text(tokens)),(item->>'embedding')::public.vector,v.source_url,v.created_at,jsonb_build_object('document_title',d.title,'catalog_revision_id',j.catalog_revision_id,'docs_target',r.docs_target,'coverage',r.coverage)
 FROM jsonb_array_elements(p_chunks) item CROSS JOIN LATERAL(SELECT app.bm25_terms(item->>'content') tokens) t,
 app.catalog_jobs j JOIN app.documents d ON d.id=j.document_id JOIN app.document_versions v ON v.id=d.active_version_id JOIN app.public_catalog_revisions r ON r.id=j.catalog_revision_id WHERE j.id=p_job
 ON CONFLICT(document_version_id,generation_id,start_offset) DO NOTHING;
 GET DIAGNOSTICS added=ROW_COUNT; RETURN added;
END $$""",
'app.catalog_activate_index(uuid,uuid,integer)':r"""
CREATE FUNCTION app.catalog_activate_index(p_job uuid,p_token uuid,p_expected integer) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE snapshot jsonb; job app.catalog_jobs%ROWTYPE;
BEGIN
 snapshot:=app.catalog_index_input(p_job,p_token);
 SELECT * INTO job FROM app.catalog_jobs WHERE id=p_job FOR UPDATE;
 IF p_expected NOT BETWEEN 1 AND 10000 OR (snapshot->>'existing_chunks')::integer<>p_expected THEN RAISE EXCEPTION 'Incomplete index' USING ERRCODE='DW021'; END IF;
 INSERT INTO app.document_indexes(document_id,generation_id,document_version_id) VALUES(job.document_id,job.generation_id,(snapshot->>'version_id')::uuid)
 ON CONFLICT(document_id,generation_id) DO UPDATE SET document_version_id=excluded.document_version_id;
 UPDATE app.documents SET status='ready' WHERE id=job.document_id;
 RETURN true;
END $$""",
'app.wake_personal_waits()':r"""
CREATE FUNCTION app.wake_personal_waits() RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE j app.personal_jobs%ROWTYPE; queued bigint; n integer:=0; project uuid;
BEGIN
 FOR j IN SELECT * FROM app.personal_jobs WHERE status='waiting' FOR UPDATE SKIP LOCKED LOOP
  SELECT project_id INTO project FROM app.conversations WHERE id=j.conversation_id AND deleted_at IS NULL;
  IF project IS NULL THEN CONTINUE; END IF;
  UPDATE app.personal_jobs SET status='queued' WHERE id=j.id;
  SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.personal',0,'personal:'||project::text,NULL,jsonb_build_object('job_id',j.id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
  n:=n+1;
 END LOOP;
 RETURN n;
END $$""",
'app.personal_catalog_state(uuid,uuid,uuid)':r"""
CREATE OR REPLACE FUNCTION app.personal_catalog_state(p_job uuid,p_token uuid,p_generation uuid) RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF app.personal_job_context(p_job,p_token) IS NULL THEN RETURN; END IF;
 RETURN QUERY SELECT to_jsonb(r)||jsonb_build_object('revision_id',r.id,'eligible',r.enabled AND r.source_approved,
 'generation_id',p_generation,'indexed_generation_id',CASE WHEN EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id)) THEN p_generation ELSE NULL END,
 'status',CASE WHEN EXISTS(SELECT 1 FROM app.collections c JOIN app.documents d ON d.collection_id=c.id JOIN app.document_indexes i ON i.document_id=d.id WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL AND i.generation_id=p_generation AND app.personal_assessment_eligible(i.document_version_id)) THEN 'indexed'
 WHEN j.status IN ('queued','running') THEN 'processing' WHEN j.status IS NULL THEN 'missing' ELSE j.status END,
 'active_job',coalesce(j.status IN ('queued','running'),false),'progress',j.stage)
 FROM app.public_catalog_revisions r LEFT JOIN app.catalog_jobs j ON j.catalog_revision_id=r.id AND j.generation_id=p_generation WHERE r.enabled AND r.source_approved;
END $$""",
}

def upgrade():
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime')
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')

def downgrade():
 for signature in reversed(FUNCTIONS):
  if signature.startswith('app.personal_catalog_state'):
   continue
  op.execute(f'DROP FUNCTION {signature}')
 # Restore the previous signature implementation before dropping catalog_jobs.
 import importlib.util
 from pathlib import Path
 spec=importlib.util.spec_from_file_location('prior_catalog',Path(__file__).with_name('0018_personal_job_context.py'))
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
 op.execute(module.FUNCTIONS['app.personal_catalog_state(uuid,uuid,uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
