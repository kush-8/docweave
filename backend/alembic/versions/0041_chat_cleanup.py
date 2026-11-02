"""Erase tombstoned chat content while retaining accounting and replay IDs."""
from alembic import op
import sqlalchemy as sa

revision = '0041_chat_cleanup'
down_revision = '0040_guardrail_lifecycle'
branch_labels = None
depends_on = None

FUNCTION = """
CREATE FUNCTION app.personal_cleanup_deleted_conversations(p_id uuid) RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 WITH candidates AS MATERIALIZED (
  SELECT c.id FROM app.conversations c WHERE c.deleted_at IS NOT NULL
  AND (p_id IS NULL OR c.id=p_id)
  AND (c.summary IS NOT NULL OR c.progress IS NOT NULL OR EXISTS(
   SELECT 1 FROM app.turns t WHERE t.conversation_id=c.id AND
   (t.message<>'' OR t.answer IS NOT NULL OR t.citations<>'[]'::jsonb
    OR t.required_dependencies<>'[]'::jsonb OR t.progress IS NOT NULL)))
  ORDER BY c.deleted_at,c.id LIMIT 100 FOR UPDATE OF c SKIP LOCKED
 ), erased_turns AS (
  UPDATE app.turns t SET message='',answer=NULL,citations='[]',required_dependencies='[]',progress=NULL
  FROM candidates c WHERE t.conversation_id=c.id RETURNING t.id
 ), erased_chats AS (
  UPDATE app.conversations c SET summary=NULL,progress=NULL FROM candidates d WHERE c.id=d.id RETURNING c.id
 ) SELECT count(*)::integer FROM erased_chats
$$
"""

MAINTENANCE = """BEGIN
 PERFORM app.personal_cleanup_deleted_conversations(NULL);
 DELETE FROM app.auth_flows WHERE state_hash IN (
  SELECT state_hash FROM app.auth_flows WHERE expires_at<=now() ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED);
 DELETE FROM app.auth_sessions WHERE token_hash IN (
  SELECT token_hash FROM app.auth_sessions WHERE expires_at<=now() ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED);
 DELETE FROM app.auth_rate_limits WHERE bucket IN (
  SELECT bucket FROM app.auth_rate_limits WHERE resets_at<=now() ORDER BY resets_at LIMIT 100 FOR UPDATE SKIP LOCKED);"""


def change(signature, before, after):
    definition = op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'), {'signature': signature})
    if before not in definition:
        raise ValueError('Unexpected chat cleanup function definition')
    op.execute(definition.replace(before, after))


def upgrade():
    op.execute(FUNCTION)
    op.execute('REVOKE ALL ON FUNCTION app.personal_cleanup_deleted_conversations(uuid) FROM PUBLIC,docweave_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_cleanup_deleted_conversations(uuid) TO docweave_worker')
    change('app.personal_delete_conversation(uuid)', ' RETURN true;',
        ' PERFORM app.personal_cleanup_deleted_conversations(p_id);\n RETURN true;')
    change('app.personal_recover_jobs()', 'BEGIN', MAINTENANCE)


def downgrade():
    change('app.personal_recover_jobs()', MAINTENANCE, 'BEGIN')
    change('app.personal_delete_conversation(uuid)', ' PERFORM app.personal_cleanup_deleted_conversations(p_id);\n RETURN true;', ' RETURN true;')
    op.execute('DROP FUNCTION app.personal_cleanup_deleted_conversations(uuid)')
