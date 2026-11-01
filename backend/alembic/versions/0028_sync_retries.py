"""Owner-only asynchronous retry of blocked repository initialization."""
from alembic import op
import sqlalchemy as sa

revision = '0028_sync_retries'
down_revision = '0027_personal_source_scope'
branch_labels = None
depends_on = None


def replace_function(signature, before, after):
    definition = op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'), {'signature': signature})
    if before not in definition:
        raise ValueError('Unexpected sync function definition')
    op.execute(definition.replace(before, after))


CHANGES = (
    ('app.personal_conversation(uuid)', "'status',c.status,", "'status',c.status,'progress',c.progress,"),
    ('app.personal_finish_job(uuid,uuid,jsonb)', "SET status='ready' WHERE id=conversation.id;", "SET status='ready',progress=NULL WHERE id=conversation.id;"),
    ('app.personal_finish_job(uuid,uuid,jsonb)', "SET status='blocked' WHERE id=conversation.id;", "SET status='blocked',progress=coalesce(p_result->>'progress','Project context changed. Retry repository synchronization.') WHERE id=conversation.id;"),
    ('app.personal_claim_job(uuid)', "SET status='blocked' WHERE id=conversation.id AND job.kind='sync';", "SET status='blocked',progress='Sign in with GitHub again, then retry repository synchronization.' WHERE id=conversation.id AND job.kind='sync';"),
)


def upgrade():
    op.add_column('conversations', sa.Column('progress', sa.Text()), schema='app')
    for signature, before, after in CHANGES:
        replace_function(signature, before, after)
    op.execute("""
CREATE FUNCTION app.personal_retry_sync(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE conversation app.conversations%ROWTYPE;
BEGIN
 SELECT * INTO conversation FROM app.conversations
 WHERE id=p_id AND deleted_at IS NULL AND app.personal_project_owned(project_id) FOR UPDATE;
 IF conversation.id IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 IF conversation.status='initializing' THEN RETURN app.personal_conversation(p_id); END IF;
 IF conversation.status<>'blocked' OR EXISTS(SELECT 1 FROM app.personal_jobs
     WHERE conversation_id=p_id AND kind='sync' AND status IN ('queued','running','waiting')) THEN
  RAISE EXCEPTION 'Sync is not retryable' USING ERRCODE='40001';
 END IF;
 UPDATE app.conversations SET status='initializing',progress=NULL WHERE id=p_id;
 PERFORM app.personal_enqueue(p_id,NULL,'sync');
 RETURN app.personal_conversation(p_id);
END $$;
""")
    op.execute('REVOKE ALL ON FUNCTION app.personal_retry_sync(uuid) FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_retry_sync(uuid) TO docweave_runtime')


def downgrade():
    op.execute('DROP FUNCTION app.personal_retry_sync(uuid)')
    for signature, before, after in reversed(CHANGES):
        replace_function(signature, after, before)
    op.drop_column('conversations', 'progress', schema='app')
