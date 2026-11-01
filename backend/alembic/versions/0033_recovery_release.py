"""Fence stale answer publication and deleted private recovery checkpoints."""
from alembic import op
import sqlalchemy as sa

revision = '0033_recovery_release'
down_revision = '0032_worker_reconciliation'
branch_labels = None
depends_on = None

# shortcut: cleanup recognizes current AnswerEngine stages; extend when adding private stages.
STAGES = "('query_resolution'),('query_embedding'),('reranking'),('generation')"
KEY_MATCH = "calls.key_hash=encode(sha256(convert_to(j.id::text||':'||stage.name,'UTF8')),'hex')"
CHANGES = (
    ('app.personal_finish_job(uuid,uuid,jsonb)', " ELSE\n  PERFORM set_config", " ELSE\n  IF coalesce((p_result->>'expected_revision')::integer,(SELECT context_revision FROM app.turns WHERE id=job.turn_id)) IS DISTINCT FROM project.context_revision THEN p_result:=jsonb_build_object('status','blocked_policy','progress','Project context changed before release. Ask again using the current context.'); END IF;\n  PERFORM set_config"),
    ('app.personal_finish_job(uuid,uuid,jsonb)', "UPDATE app.turns SET status=p_result->>'status'", "UPDATE app.turns SET context_revision=CASE WHEN p_result->>'status' IN ('completed','waiting_for_sources') THEN project.context_revision ELSE context_revision END,status=p_result->>'status'"),
    ('app.personal_delete_conversation(uuid)', "BEGIN\n UPDATE app.conversations", "BEGIN\n PERFORM j.id FROM app.personal_jobs j JOIN app.conversations c ON c.id=j.conversation_id WHERE c.id=p_id AND app.personal_project_owned(c.project_id) ORDER BY j.id FOR UPDATE OF j;\n UPDATE app.conversations"),
    ('app.personal_delete_conversation(uuid)', ' RETURN true;', f" UPDATE app.personal_provider_calls calls SET response=NULL WHERE EXISTS(SELECT 1 FROM app.personal_jobs j CROSS JOIN (VALUES {STAGES}) stage(name) WHERE j.conversation_id=p_id AND {KEY_MATCH});\n RETURN true;"),
    ('app.personal_provider_checkpoint(uuid,jsonb)', 'BEGIN\n IF p_response', f"""BEGIN
 IF EXISTS(SELECT 1 FROM app.cost_reservations WHERE id=p_id AND project_id IS NOT NULL) THEN
  PERFORM c.id FROM app.personal_provider_calls calls JOIN app.cost_reservations r ON r.id=calls.reservation_id
   JOIN app.personal_jobs j ON j.actor_id=r.actor_id JOIN app.conversations c ON c.id=j.conversation_id AND c.project_id=r.project_id
   JOIN app.projects p ON p.id=c.project_id AND p.owner_user_id=r.actor_id CROSS JOIN (VALUES {STAGES}) stage(name)
   WHERE r.id=p_id AND {KEY_MATCH} AND c.deleted_at IS NULL AND j.status='running' AND j.lease_expires_at>now() FOR SHARE OF c;
  IF NOT FOUND THEN RAISE EXCEPTION 'Recovery authority changed' USING ERRCODE='42501'; END IF;
 END IF;
 IF p_response"""),
)


def change(signature, before, after):
    definition = op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'), {'signature': signature})
    if before not in definition:
        raise ValueError('Unexpected recovery function definition')
    op.execute(definition.replace(before, after))


def upgrade():
    for signature, before, after in CHANGES:
        change(signature, before, after)


def downgrade():
    for signature, before, after in reversed(CHANGES):
        change(signature, after, before)
