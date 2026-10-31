"""Global conservative provider admission without tenant quotas or paid tiers."""
from alembic import op
import sqlalchemy as sa
revision='0021_personal_provider_admission'
down_revision='0020_catalog_publication'
branch_labels=None
depends_on=None

def upgrade():
 op.alter_column('cost_reservations','workspace_id',nullable=True,schema='app')
 op.create_index('uq_personal_cost_operation','cost_reservations',['actor_id','operation_hash'],unique=True,postgresql_where=sa.text('workspace_id IS NULL'),schema='app')
 for table in ('project_processor_approvals','collection_processor_approvals'):
  op.alter_column(table,'workspace_id',nullable=True,schema='app')
 op.create_table('personal_provider_calls',sa.Column('operation_hash',sa.Text(),primary_key=True),sa.Column('body_hash',sa.Text(),nullable=False),sa.Column('reservation_id',sa.UUID(),sa.ForeignKey('app.cost_reservations.id',ondelete='RESTRICT'),nullable=False),schema='app')
 op.execute('ALTER TABLE app.personal_provider_calls ENABLE ROW LEVEL SECURITY')
 op.execute('REVOKE ALL ON app.personal_provider_calls FROM PUBLIC,docweave_runtime,docweave_worker')
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  role='docweave_runtime' if signature.startswith(('app.personal_processing_policy','app.personal_replace_processing_policy')) else 'docweave_worker'
  op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {role}')

FUNCTIONS={
'app.personal_processing_policy(uuid)':r"""
CREATE FUNCTION app.personal_processing_policy(p_project uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('revision',p.processing_revision,'processor_ids',coalesce((SELECT jsonb_agg(processor_id ORDER BY processor_id) FROM app.project_processor_approvals WHERE project_id=p.id),'[]')) FROM app.projects p WHERE p.id=p_project AND app.personal_project_owned(p.id)
$$""",
'app.personal_replace_processing_policy(uuid,integer,jsonb)':r"""
CREATE FUNCTION app.personal_replace_processing_policy(p_project uuid,p_revision integer,p_processors jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p app.projects%ROWTYPE; wanted text;
BEGIN
 SELECT * INTO p FROM app.projects WHERE id=p_project AND app.personal_project_owned(id) FOR UPDATE;
 IF p.id IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 IF p.processing_revision<>p_revision THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='DW003'; END IF;
 IF jsonb_typeof(p_processors)<>'array' OR jsonb_array_length(p_processors)>50 OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_processors) v WHERE jsonb_typeof(v)<>'string') THEN RAISE EXCEPTION 'Invalid processors' USING ERRCODE='22023'; END IF;
 DELETE FROM app.project_processor_approvals WHERE project_id=p.id;
 DELETE FROM app.collection_processor_approvals WHERE collection_id IN(SELECT id FROM app.collections WHERE project_id=p.id);
 FOR wanted IN SELECT DISTINCT jsonb_array_elements_text(p_processors) LOOP
  IF NOT EXISTS(SELECT 1 FROM app.processors WHERE id=wanted AND enabled) THEN RAISE EXCEPTION 'Processor unavailable' USING ERRCODE='22023'; END IF;
  INSERT INTO app.project_processor_approvals(project_id,workspace_id,processor_id,approved_by) VALUES(p.id,p.workspace_id,wanted,p.owner_user_id);
  INSERT INTO app.collection_processor_approvals(collection_id,workspace_id,processor_id,approved_by) SELECT id,workspace_id,wanted,p.owner_user_id FROM app.collections WHERE project_id=p.id;
 END LOOP;
 UPDATE app.projects SET processing_revision=processing_revision+1 WHERE id=p.id;
 RETURN app.personal_processing_policy(p.id);
END $$""",
'app.personal_provider_claim(uuid,uuid,uuid,text,text,integer,integer)':r"""
CREATE FUNCTION app.personal_provider_claim(p_project uuid,p_actor uuid,p_profile uuid,p_operation text,p_body text,p_input integer,p_output integer) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE profile app.provider_profiles%ROWTYPE; reservation uuid; maximum numeric; spent numeric;
BEGIN
 PERFORM app.lock_budget();
 IF p_operation !~ '^[0-9a-f]{64}$' OR p_body !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'Invalid request identity' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM app.personal_provider_calls WHERE operation_hash=p_operation) THEN RAISE EXCEPTION 'Operation already claimed' USING ERRCODE='DW014'; END IF;
 SELECT * INTO profile FROM app.provider_profiles WHERE id=p_profile FOR SHARE;
 IF profile.id IS NULL OR app.profile_disabled_reason(profile.id) IS NOT NULL OR p_input NOT BETWEEN 1 AND profile.max_input_tokens OR p_output NOT BETWEEN 0 AND profile.max_output_tokens THEN RAISE EXCEPTION 'Profile unavailable' USING ERRCODE='DW013'; END IF;
 IF p_project IS NULL THEN
  IF p_actor<>'60000000-0000-4000-8000-000000000001'::uuid OR profile.role<>'embedding' THEN RAISE EXCEPTION 'Invalid public processing' USING ERRCODE='42501'; END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM app.projects WHERE id=p_project AND owner_user_id=p_actor) OR EXISTS(
   SELECT 1 FROM jsonb_array_elements_text(profile.processor_ids) wanted(id) WHERE NOT EXISTS(SELECT 1 FROM app.project_processor_approvals a WHERE a.project_id=p_project AND a.processor_id=wanted.id)) THEN RAISE EXCEPTION 'Processing approval required' USING ERRCODE='DW020'; END IF;
 END IF;
 maximum:=ceil(((p_input*profile.input_usd_per_million+p_output*profile.output_usd_per_million)/1000000+profile.fixed_usd)*profile.max_attempts*1000000000000)/1000000000000;
 SELECT coalesce(sum(charged_usd),0) INTO spent FROM app.cost_reservations WHERE month=app.budget_month(statement_timestamp());
 IF spent+maximum>20 THEN RAISE EXCEPTION 'Application capacity unavailable' USING ERRCODE='DW012'; END IF;
 INSERT INTO app.cost_reservations(actor_id,project_id,profile_id,operation_hash,month,input_tokens,output_tokens,maximum_usd,status) VALUES(p_actor,p_project,p_profile,p_operation,app.budget_month(statement_timestamp()),p_input,p_output,maximum,'uncertain') RETURNING id INTO reservation;
 INSERT INTO app.personal_provider_calls(operation_hash,body_hash,reservation_id) VALUES(p_operation,p_body,reservation);
 RETURN jsonb_build_object('id',reservation,'provider',profile.provider,'model',profile.model,'role',profile.role,'maximum_usd',maximum::text,'input_rate',profile.input_usd_per_million::text,'output_rate',profile.output_usd_per_million::text,'fixed_usd',profile.fixed_usd::text);
END $$""",
'app.personal_provider_settle(uuid,numeric)':r"""
CREATE FUNCTION app.personal_provider_settle(p_id uuid,p_actual numeric) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE reservation app.cost_reservations%ROWTYPE;
BEGIN
 PERFORM app.lock_budget();
 SELECT r.* INTO reservation FROM app.cost_reservations r JOIN app.personal_provider_calls c ON c.reservation_id=r.id WHERE r.id=p_id FOR UPDATE OF r;
 IF reservation.id IS NULL OR p_actual IS NULL OR p_actual<0 OR p_actual>=1000000000000 OR reservation.status='metered' AND reservation.actual_usd<>p_actual THEN RAISE EXCEPTION 'Invalid settlement' USING ERRCODE='22023'; END IF;
 UPDATE app.cost_reservations SET status='metered',actual_usd=p_actual WHERE id=p_id;
 IF p_actual>reservation.maximum_usd THEN UPDATE app.provider_profiles SET enabled=false WHERE id=reservation.profile_id; END IF;
END $$""",
}

def downgrade():
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
 op.drop_table('personal_provider_calls',schema='app')
 op.drop_index('uq_personal_cost_operation',table_name='cost_reservations',schema='app')
 op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.cost_reservations WHERE workspace_id IS NULL) OR EXISTS(SELECT 1 FROM app.project_processor_approvals WHERE workspace_id IS NULL) OR EXISTS(SELECT 1 FROM app.collection_processor_approvals WHERE workspace_id IS NULL) THEN RAISE EXCEPTION 'Preserve personal accounting/consent before downgrade'; END IF; END $$")
 for table in ('cost_reservations','project_processor_approvals','collection_processor_approvals'):
  op.alter_column(table,'workspace_id',nullable=False,schema='app')
