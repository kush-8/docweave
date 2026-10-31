"""Separate approved public-fixture pilot capacity from fixed synthetic probes."""

from alembic import op
import sqlalchemy as sa

revision = "0012_public_pilot_budget"
down_revision = "0011_compatibility_probes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("compatibility_requests", sa.Column("purpose", sa.Text(), nullable=False, server_default=sa.text("'synthetic'")), schema="app")
    op.create_check_constraint("valid_purpose", "compatibility_requests", "purpose IN ('synthetic','public_fixture')", schema="app")
    op.execute(PUBLIC_RESERVE)


def downgrade():
    op.execute(PREVIOUS_RESERVE)
    op.drop_constraint("valid_purpose", "compatibility_requests", schema="app", type_="check")
    op.drop_column("compatibility_requests", "purpose", schema="app")

PREVIOUS_RESERVE = """

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

PUBLIC_RESERVE = """

        CREATE OR REPLACE FUNCTION app.reserve_cost(p_hash text,p_profile uuid,p_input integer,p_output integer,p_project uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE actor uuid:=nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace uuid:=nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            prior app.cost_reservations%ROWTYPE; profile app.provider_profiles%ROWTYPE; billing_month date;
            allowance numeric; maximum numeric; workspace_used numeric; global_used numeric; reservation uuid; probe boolean; probe_purpose text;
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
            probe_purpose := (SELECT purpose FROM app.compatibility_requests WHERE operation_hash=p_hash);
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
                    ON c.operation_hash=r.operation_hash AND c.profile_id=r.profile_id WHERE c.purpose=probe_purpose)
                >(CASE WHEN probe_purpose='public_fixture' THEN 1 ELSE 0.25 END) THEN
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
