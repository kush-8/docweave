"""Reconcile original jobs after missed delivery and lease expiry."""
from alembic import op

revision = '0032_worker_reconciliation'
down_revision = '0031_worker_recovery'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE FUNCTION app.personal_recover_jobs() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE j record; n integer:=0; queued bigint;
BEGIN
 FOR j IN SELECT jobs.id,c.project_id FROM app.personal_jobs jobs JOIN app.conversations c ON c.id=jobs.conversation_id
  JOIN app.projects p ON p.id=c.project_id WHERE c.deleted_at IS NULL AND p.owner_user_id=jobs.actor_id
  AND (jobs.status IN ('queued','waiting') OR jobs.status='running' AND jobs.lease_expires_at<now())
  AND NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.personal' AND q.args->>'job_id'=jobs.id::text AND q.status IN ('todo','doing'))
  ORDER BY coalesce((SELECT max(q.id) FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.personal' AND q.args->>'job_id'=jobs.id::text),0),jobs.created_at,jobs.id LIMIT 100 FOR UPDATE OF jobs SKIP LOCKED LOOP
  IF NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.personal'
    AND q.args->>'job_id'=j.id::text AND q.status IN ('todo','doing')) THEN
   SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.personal',0,'personal:'||j.project_id::text,NULL,jsonb_build_object('job_id',j.id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
   n:=n+1;
  END IF;
 END LOOP;
 FOR j IN SELECT jobs.id FROM app.catalog_jobs jobs JOIN app.public_catalog_revisions r ON r.id=jobs.catalog_revision_id
  JOIN app.index_generations g ON g.id=jobs.generation_id WHERE r.enabled AND r.source_approved AND g.enabled
  AND (jobs.status IN ('queued','capacity') OR jobs.status='running' AND jobs.lease_expires_at<now())
  AND NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.catalog' AND q.args->>'job_id'=jobs.id::text AND q.status IN ('todo','doing'))
  ORDER BY coalesce((SELECT max(q.id) FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.catalog' AND q.args->>'job_id'=jobs.id::text),0),jobs.created_at,jobs.id LIMIT 100 FOR UPDATE OF jobs SKIP LOCKED LOOP
  IF NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.catalog'
    AND q.args->>'job_id'=j.id::text AND q.status IN ('todo','doing')) THEN
   SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.catalog',0,'public-catalog',NULL,jsonb_build_object('job_id',j.id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
   n:=n+1;
  END IF;
 END LOOP;
 RETURN n;
END $$""")
    op.execute('REVOKE ALL ON FUNCTION app.personal_recover_jobs() FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_recover_jobs() TO docweave_worker')


def downgrade():
    op.execute('DROP FUNCTION app.personal_recover_jobs()')
