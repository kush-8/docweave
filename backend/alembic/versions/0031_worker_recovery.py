"""Private response checkpoints and bounded durable job reconciliation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0031_worker_recovery'
down_revision = '0030_documentation_review'
branch_labels = None
depends_on = None

FUNCTIONS = {
'app.personal_provider_resume(uuid,uuid,uuid,text,text,integer,integer,text)': """
CREATE FUNCTION app.personal_provider_resume(p_project uuid,p_actor uuid,p_profile uuid,p_operation text,p_body text,p_input integer,p_output integer,p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE old app.personal_provider_calls%ROWTYPE; claim app.cost_reservations%ROWTYPE; profile app.provider_profiles%ROWTYPE; result jsonb;
BEGIN
 PERFORM app.lock_budget();
 IF p_key IS NULL OR p_key !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'Invalid operation key' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM app.personal_provider_calls c JOIN app.cost_reservations r ON r.id=c.reservation_id
  WHERE c.response IS NULL AND (c.key_hash=p_key OR c.key_hash IS NULL AND r.actor_id=p_actor AND r.project_id IS NOT DISTINCT FROM p_project)) THEN
  RAISE EXCEPTION 'Uncertain operation' USING ERRCODE='DW014';
 END IF;
 SELECT * INTO old FROM app.personal_provider_calls WHERE operation_hash=p_operation;
 IF old.operation_hash IS NOT NULL THEN
  SELECT * INTO claim FROM app.cost_reservations WHERE id=old.reservation_id;
  SELECT * INTO profile FROM app.provider_profiles WHERE id=p_profile;
  IF old.body_hash<>p_body OR old.key_hash<>p_key OR claim.actor_id<>p_actor OR claim.project_id IS DISTINCT FROM p_project OR claim.profile_id<>p_profile
   OR old.response IS NULL THEN RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014'; END IF;
  IF profile.id IS NULL OR app.profile_disabled_reason(p_profile) IS NOT NULL THEN RAISE EXCEPTION 'Profile unavailable' USING ERRCODE='DW013'; END IF;
  IF p_project IS NULL THEN
   IF p_actor<>'60000000-0000-4000-8000-000000000001'::uuid OR profile.role<>'embedding' THEN RAISE EXCEPTION 'Invalid public processing' USING ERRCODE='42501'; END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM app.projects WHERE id=p_project AND owner_user_id=p_actor) OR EXISTS(
    SELECT 1 FROM jsonb_array_elements_text(profile.processor_ids) wanted(id) WHERE NOT EXISTS(
     SELECT 1 FROM app.project_processor_approvals a WHERE a.project_id=p_project AND a.processor_id=wanted.id)) THEN
   RAISE EXCEPTION 'Processing approval required' USING ERRCODE='DW020';
  END IF;
  RETURN jsonb_build_object('response',old.response);
 END IF;
 result:=app.personal_provider_claim(p_project,p_actor,p_profile,p_operation,p_body,p_input,p_output);
 UPDATE app.personal_provider_calls SET key_hash=p_key WHERE operation_hash=p_operation;
 RETURN result;
END $$""",
'app.personal_provider_checkpoint(uuid,jsonb)': """
CREATE FUNCTION app.personal_provider_checkpoint(p_id uuid,p_response jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF p_response IS NULL OR jsonb_typeof(p_response)<>'object' OR octet_length(p_response::text)>2097152 THEN
  RAISE EXCEPTION 'Invalid response checkpoint' USING ERRCODE='22023'; END IF;
 UPDATE app.personal_provider_calls SET response=p_response WHERE reservation_id=p_id AND (response IS NULL OR response=p_response);
 IF NOT FOUND THEN RAISE EXCEPTION 'Response conflict' USING ERRCODE='22023'; END IF;
END $$""",
}


def upgrade():
    op.add_column('personal_provider_calls', sa.Column('key_hash', sa.Text()), schema='app')
    op.add_column('personal_provider_calls', sa.Column('response', JSONB()), schema='app')
    op.create_index('ix_personal_provider_key', 'personal_provider_calls', ['key_hash'], schema='app')
    for signature, definition in FUNCTIONS.items():
        op.execute(definition)
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.personal_provider_calls WHERE response IS NOT NULL) THEN RAISE EXCEPTION 'Preserve response checkpoints before downgrade'; END IF; END $$")
    for signature in reversed(FUNCTIONS):
        op.execute(f'DROP FUNCTION {signature}')
    op.drop_index('ix_personal_provider_key', table_name='personal_provider_calls', schema='app')
    for column in ('response', 'key_hash'):
        op.drop_column('personal_provider_calls', column, schema='app')
