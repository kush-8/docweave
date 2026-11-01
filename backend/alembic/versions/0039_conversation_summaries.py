"""Lease-fenced, revision-bound private conversation summaries."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0039_conversation_summaries'
down_revision = '0038_openai_embeddings'
branch_labels = None
depends_on = None

FUNCTION = r"""
CREATE FUNCTION app.personal_worker_summary(p_job uuid,p_token uuid,p_revision integer,p_summary jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE context jsonb; j app.personal_jobs%ROWTYPE; c app.conversations%ROWTYPE; current_revision integer;
BEGIN
 context:=app.personal_job_context(p_job,p_token);
 IF context IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO j FROM app.personal_jobs WHERE id=p_job AND kind='answer';
 IF j.id IS NULL THEN RETURN NULL; END IF;
 SELECT context_revision INTO current_revision FROM app.projects
 WHERE id=(context->'project'->>'id')::uuid FOR SHARE;
 SELECT * INTO c FROM app.conversations WHERE id=j.conversation_id AND deleted_at IS NULL FOR UPDATE;
 IF c.id IS NULL OR current_revision IS DISTINCT FROM p_revision THEN RETURN NULL; END IF;
 IF p_summary IS NULL THEN
  RETURN CASE WHEN (c.summary->>'context_revision')::integer=p_revision THEN c.summary ELSE NULL END;
 END IF;
 IF jsonb_typeof(p_summary)<>'object' OR octet_length(p_summary::text)>32768
 OR NOT(p_summary ?& ARRAY['context_revision','through_sequence','history_hash','prompt_version','text'])
 OR (p_summary->>'context_revision')::integer IS DISTINCT FROM p_revision
 OR jsonb_typeof(p_summary->'text')<>'string' OR length(p_summary->>'text')=0
 OR p_summary->>'history_hash' !~ '^[0-9a-f]{64}$'
 OR NOT EXISTS(SELECT 1 FROM app.turns WHERE conversation_id=c.id AND status='completed'
   AND sequence=(p_summary->>'through_sequence')::integer
   AND sequence<(SELECT sequence FROM app.turns WHERE id=j.turn_id)) THEN
  RAISE EXCEPTION 'Invalid conversation summary' USING ERRCODE='22023';
 END IF;
 IF EXISTS(SELECT 1 FROM app.turns t WHERE t.conversation_id=c.id
   AND t.sequence<=(p_summary->>'through_sequence')::integer
   AND app.personal_turn(t.id)->>'status'='blocked_policy') THEN RETURN NULL; END IF;
 UPDATE app.conversations SET summary=p_summary WHERE id=c.id;
 RETURN p_summary;
END $$
"""


def replace_stages(before, after):
    # Keep summary response recovery and deletion under the same authority as other private stages.
    for signature in ('app.personal_provider_checkpoint(uuid,jsonb)', 'app.personal_delete_conversation(uuid)'):
        definition = op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'), {'signature': signature})
        if before not in definition:
            raise ValueError('Unexpected private recovery stages')
        op.execute(definition.replace(before, after))


def upgrade():
    op.add_column('conversations', sa.Column('summary', JSONB()), schema='app')
    op.execute(FUNCTION)
    op.execute('REVOKE ALL ON FUNCTION app.personal_worker_summary(uuid,uuid,integer,jsonb) FROM PUBLIC,docweave_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_worker_summary(uuid,uuid,integer,jsonb) TO docweave_worker')
    replace_stages("('query_resolution')", "('summarization'),('query_resolution')")
    definition = op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('app.personal_delete_conversation(uuid)'::regprocedure)"))
    op.execute(definition.replace("SET deleted_at=now(),status='deleted'", "SET deleted_at=now(),status='deleted',summary=NULL"))


def downgrade():
    definition = op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('app.personal_delete_conversation(uuid)'::regprocedure)"))
    op.execute(definition.replace(",summary=NULL", ""))
    replace_stages("('summarization'),('query_resolution')", "('query_resolution')")
    op.execute('DROP FUNCTION app.personal_worker_summary(uuid,uuid,integer,jsonb)')
    op.drop_column('conversations', 'summary', schema='app')
