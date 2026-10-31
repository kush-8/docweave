"""Private fixed-input operator probes; shared durable financial limits remain enforced."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_compatibility_probes"
down_revision = "0010_provider_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("compatibility_requests",
        sa.Column("operation_hash", sa.Text(), primary_key=True), sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.UUID(), sa.ForeignKey("app.provider_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False), sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.CheckConstraint("operation_hash ~ '^[0-9a-f]{64}$' AND request_hash ~ '^[0-9a-f]{64}$'", name="valid_hashes"),
        sa.CheckConstraint("input_tokens BETWEEN 0 AND 1000000000 AND output_tokens BETWEEN 0 AND 1000000000", name="valid_tokens"), schema="app")
    op.create_table("compatibility_operations",
        sa.Column("reservation_id", sa.UUID(), sa.ForeignKey("app.cost_reservations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("request_hash", sa.Text(), nullable=False), sa.Column("result", JSONB()),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="valid_hash"),
        sa.CheckConstraint("result IS NULL OR (jsonb_typeof(result)='object' AND octet_length(result::text)<=65536)", name="bounded_result"), schema="app")
    op.execute("REVOKE ALL ON app.compatibility_requests,app.compatibility_operations FROM PUBLIC,docweave_runtime,docweave_worker")
    op.execute("""
        CREATE FUNCTION app.freeze_consumed_probe() RETURNS trigger LANGUAGE plpgsql
        SET search_path=pg_catalog,app AS $$
        BEGIN
            PERFORM app.lock_budget();
            IF EXISTS (SELECT 1 FROM app.cost_reservations r WHERE r.operation_hash=OLD.operation_hash AND r.profile_id=OLD.profile_id) THEN
                RAISE EXCEPTION 'Consumed probe registration is immutable' USING ERRCODE='22023'; END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION app.freeze_consumed_probe() FROM PUBLIC,docweave_runtime,docweave_worker")
    op.execute("CREATE TRIGGER freeze_consumed_probe BEFORE UPDATE OR DELETE ON app.compatibility_requests FOR EACH ROW EXECUTE FUNCTION app.freeze_consumed_probe()")
    op.execute(PROBE_RESERVE)
    op.execute("""
        CREATE FUNCTION app.claim_compatibility_probe(p_hash text,p_request text,p_project uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE request app.compatibility_requests%ROWTYPE; reservation jsonb; operation app.compatibility_operations%ROWTYPE;
            added integer;
        BEGIN
            PERFORM app.lock_budget();
            SELECT * INTO request FROM app.compatibility_requests WHERE operation_hash=p_hash;
            IF NOT FOUND OR request.request_hash IS DISTINCT FROM p_request THEN
                RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014'; END IF;
            reservation:=app.reserve_cost(p_hash,request.profile_id,request.input_tokens,request.output_tokens,p_project);
            INSERT INTO app.compatibility_operations(reservation_id,request_hash)
                VALUES ((reservation->>'id')::uuid,p_request) ON CONFLICT DO NOTHING;
            GET DIAGNOSTICS added=ROW_COUNT;
            SELECT * INTO operation FROM app.compatibility_operations WHERE reservation_id=(reservation->>'id')::uuid;
            IF operation.request_hash IS DISTINCT FROM p_request THEN RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014'; END IF;
            IF added=1 THEN reservation:=app.settle_cost((reservation->>'id')::uuid,NULL,true); END IF;
            RETURN jsonb_build_object('created',added=1,'reservation',reservation,'result',operation.result);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.complete_compatibility_probe(p_reservation uuid,p_result jsonb,p_actual numeric,p_uncertain boolean)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE operation app.compatibility_operations%ROWTYPE;
        BEGIN
            PERFORM app.lock_budget();
            SELECT * INTO operation FROM app.compatibility_operations WHERE reservation_id=p_reservation FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_result IS NULL OR jsonb_typeof(p_result)<>'object' OR octet_length(p_result::text)>65536
                OR p_result->>'outcome' IS NULL OR p_result->>'outcome' NOT IN ('succeeded','rejected','completion_unknown') THEN
                RAISE EXCEPTION 'Invalid result' USING ERRCODE='22023'; END IF;
            IF operation.result IS NOT NULL AND operation.result IS DISTINCT FROM p_result THEN
                RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014'; END IF;
            PERFORM app.settle_cost(p_reservation,p_actual,p_uncertain);
            UPDATE app.compatibility_operations SET result=p_result WHERE reservation_id=p_reservation;
        END $$
    """)
    for signature in ("app.claim_compatibility_probe(text,text,uuid)", "app.complete_compatibility_probe(uuid,jsonb,numeric,boolean)"):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker")


def downgrade():
    op.execute(ORIGINAL_RESERVE)
    op.execute("DROP TRIGGER freeze_consumed_probe ON app.compatibility_requests")
    op.execute("DROP FUNCTION app.freeze_consumed_probe()")
    op.execute("DROP FUNCTION app.complete_compatibility_probe(uuid,jsonb,numeric,boolean)")
    op.execute("DROP FUNCTION app.claim_compatibility_probe(text,text,uuid)")
    op.drop_table("compatibility_operations", schema="app")
    op.drop_table("compatibility_requests", schema="app")

ORIGINAL_RESERVE = """
        CREATE OR REPLACE FUNCTION app.reserve_cost(p_hash text,p_profile uuid,p_input integer,p_output integer,p_project uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE actor uuid:=nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace uuid:=nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            prior app.cost_reservations%ROWTYPE; profile app.provider_profiles%ROWTYPE; billing_month date;
            allowance numeric; maximum numeric; workspace_used numeric; global_used numeric; reservation uuid;
        BEGIN
            PERFORM app.lock_budget();
            PERFORM 1 FROM app.workspaces WHERE id=workspace FOR UPDATE;
            IF NOT EXISTS (SELECT 1 FROM app.memberships WHERE workspace_id=workspace AND user_id=actor) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_project IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app.projects WHERE id=p_project AND workspace_id=workspace) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' OR p_input IS NULL OR p_output IS NULL OR p_input<0 OR p_output<0 THEN RAISE EXCEPTION 'Invalid request' USING ERRCODE='22023'; END IF;
            SELECT * INTO prior FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.operation_hash=p_hash;
            IF FOUND THEN
                IF (prior.actor_id,prior.profile_id,prior.input_tokens,prior.output_tokens,prior.project_id) IS DISTINCT FROM (actor,p_profile,p_input,p_output,p_project) THEN
                    RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014';
                END IF;
                RETURN app.reservation_view(prior.id,false);
            END IF;
            SELECT * INTO profile FROM app.provider_profiles WHERE id=p_profile;
            IF NOT FOUND OR app.profile_disabled_reason(p_profile) IS NOT NULL THEN RAISE EXCEPTION 'Profile unavailable' USING ERRCODE='DW013'; END IF;
            IF p_input>profile.max_input_tokens OR p_output>profile.max_output_tokens THEN RAISE EXCEPTION 'Token bounds exceeded' USING ERRCODE='22023'; END IF;
            maximum:=ceil(((p_input*profile.input_usd_per_million+p_output*profile.output_usd_per_million)/1000000+profile.fixed_usd)*profile.max_attempts*1000000000000)/1000000000000;
            billing_month:=app.budget_month(clock_timestamp());
            SELECT a.allowance_usd INTO allowance FROM app.workspace_allowances a WHERE a.workspace_id=workspace AND a.month=billing_month;
            IF allowance IS NULL THEN RAISE EXCEPTION 'Allowance required' USING ERRCODE='DW010'; END IF;
            SELECT coalesce(sum(r.charged_usd),0) INTO workspace_used FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.month=billing_month;
            IF allowance<=0 OR workspace_used+maximum>allowance THEN RAISE EXCEPTION 'Workspace limit' USING ERRCODE='DW011'; END IF;
            SELECT coalesce(sum(r.charged_usd),0) INTO global_used FROM app.cost_reservations r WHERE r.month=billing_month;
            IF global_used+maximum>20 THEN RAISE EXCEPTION 'Application capacity unavailable' USING ERRCODE='DW012'; END IF;
            INSERT INTO app.cost_reservations(workspace_id,actor_id,project_id,profile_id,operation_hash,month,input_tokens,output_tokens,maximum_usd,created_at)
                VALUES (workspace,actor,p_project,p_profile,p_hash,billing_month,p_input,p_output,maximum,clock_timestamp()) RETURNING id INTO reservation;
            RETURN app.reservation_view(reservation,true);
        END $$
"""

PROBE_RESERVE = """
        CREATE OR REPLACE FUNCTION app.reserve_cost(p_hash text,p_profile uuid,p_input integer,p_output integer,p_project uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE actor uuid:=nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace uuid:=nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            prior app.cost_reservations%ROWTYPE; profile app.provider_profiles%ROWTYPE; billing_month date;
            allowance numeric; maximum numeric; workspace_used numeric; global_used numeric; reservation uuid; probe boolean;
        BEGIN
            PERFORM app.lock_budget();
            PERFORM 1 FROM app.workspaces WHERE id=workspace FOR UPDATE;
            IF NOT EXISTS (SELECT 1 FROM app.memberships WHERE workspace_id=workspace AND user_id=actor) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_project IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app.projects WHERE id=p_project AND workspace_id=workspace) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' OR p_input IS NULL OR p_output IS NULL OR p_input<0 OR p_output<0 THEN RAISE EXCEPTION 'Invalid request' USING ERRCODE='22023'; END IF;
            SELECT * INTO prior FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.operation_hash=p_hash;
            IF FOUND THEN
                IF (prior.actor_id,prior.profile_id,prior.input_tokens,prior.output_tokens,prior.project_id) IS DISTINCT FROM (actor,p_profile,p_input,p_output,p_project) THEN
                    RAISE EXCEPTION 'Operation conflict' USING ERRCODE='DW014';
                END IF;
                RETURN app.reservation_view(prior.id,false);
            END IF;
            SELECT * INTO profile FROM app.provider_profiles WHERE id=p_profile;
            probe := session_user='docweave_migrator' AND EXISTS (
                SELECT 1 FROM app.compatibility_requests c WHERE c.operation_hash=p_hash AND c.profile_id=p_profile
                    AND c.input_tokens=p_input AND c.output_tokens=p_output);
            IF profile.id IS NULL OR (app.profile_disabled_reason(p_profile) IS NOT NULL AND NOT probe)
                OR (probe AND (NOT profile.pricing_verified OR profile.input_usd_per_million IS NULL
                    OR profile.output_usd_per_million IS NULL OR profile.fixed_usd IS NULL
                    OR profile.max_input_tokens IS NULL OR profile.max_output_tokens IS NULL OR profile.max_attempts<>1
                    OR EXISTS (SELECT 1 FROM app.cost_reservations r WHERE r.profile_id=p_profile AND r.actual_usd>r.maximum_usd)))
                THEN RAISE EXCEPTION 'Profile unavailable' USING ERRCODE='DW013'; END IF;
            IF p_input>profile.max_input_tokens OR p_output>profile.max_output_tokens THEN RAISE EXCEPTION 'Token bounds exceeded' USING ERRCODE='22023'; END IF;
            maximum:=ceil(((p_input*profile.input_usd_per_million+p_output*profile.output_usd_per_million)/1000000+profile.fixed_usd)*profile.max_attempts*1000000000000)/1000000000000;
            IF probe AND maximum+(SELECT coalesce(sum(greatest(r.maximum_usd,r.charged_usd)),0)
                FROM app.cost_reservations r JOIN app.compatibility_requests c
                    ON c.operation_hash=r.operation_hash AND c.profile_id=r.profile_id)>0.25 THEN
                RAISE EXCEPTION 'Probe limit' USING ERRCODE='DW016'; END IF;
            billing_month:=app.budget_month(clock_timestamp());
            SELECT a.allowance_usd INTO allowance FROM app.workspace_allowances a WHERE a.workspace_id=workspace AND a.month=billing_month;
            IF allowance IS NULL THEN RAISE EXCEPTION 'Allowance required' USING ERRCODE='DW010'; END IF;
            SELECT coalesce(sum(r.charged_usd),0) INTO workspace_used FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.month=billing_month;
            IF allowance<=0 OR workspace_used+maximum>allowance THEN RAISE EXCEPTION 'Workspace limit' USING ERRCODE='DW011'; END IF;
            SELECT coalesce(sum(r.charged_usd),0) INTO global_used FROM app.cost_reservations r WHERE r.month=billing_month;
            IF global_used+maximum>20 THEN RAISE EXCEPTION 'Application capacity unavailable' USING ERRCODE='DW012'; END IF;
            INSERT INTO app.cost_reservations(workspace_id,actor_id,project_id,profile_id,operation_hash,month,input_tokens,output_tokens,maximum_usd,created_at)
                VALUES (workspace,actor,p_project,p_profile,p_hash,billing_month,p_input,p_output,maximum,clock_timestamp()) RETURNING id INTO reservation;
            RETURN app.reservation_view(reservation,true);
        END $$
"""
