"""Private conservative financial admission and immutable configured profiles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_budget"
down_revision = "0006_collection_policy"
branch_labels = None
depends_on = None

FUNCTIONS = ("app.budget_month(timestamptz)", "app.lock_budget()", "app.immutable_profile()",
    "app.profile_disabled_reason(uuid)", "app.set_workspace_allowance(uuid,date,numeric)",
    "app.reservation_view(uuid,boolean)", "app.reserve_cost(text,uuid,integer,integer,uuid)",
    "app.settle_cost(uuid,numeric,boolean)", "app.usage_report(date,uuid)")
PRIVATE = {"app.lock_budget()", "app.immutable_profile()", "app.set_workspace_allowance(uuid,date,numeric)", "app.reservation_view(uuid,boolean)"}


def upgrade():
    op.create_table("provider_profiles",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("provider", sa.Text(), nullable=False), sa.Column("model", sa.Text(), nullable=False),
        sa.Column("backend", sa.Text(), nullable=False), sa.Column("role", sa.Text(), nullable=False),
        sa.Column("processor_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("input_usd_per_million", sa.Numeric()), sa.Column("output_usd_per_million", sa.Numeric()),
        sa.Column("fixed_usd", sa.Numeric()), sa.Column("max_input_tokens", sa.Integer()), sa.Column("max_output_tokens", sa.Integer()),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        *[sa.Column(flag, sa.Boolean(), nullable=False, server_default=sa.text("false")) for flag in ("enabled", "capabilities_verified", "account_verified", "pricing_verified")],
        sa.CheckConstraint("provider IN ('gemini','groq','huggingface')", name=op.f("ck_provider_profiles_valid_provider")),
        sa.CheckConstraint("model ~ '[^[:space:]]' AND backend ~ '[^[:space:]]'", name=op.f("ck_provider_profiles_nonblank_identity")),
        sa.CheckConstraint("role IN ('embedding','reranking','query_resolution','summarization','generation')", name=op.f("ck_provider_profiles_valid_role")),
        sa.CheckConstraint("jsonb_typeof(processor_ids)='array'", name=op.f("ck_provider_profiles_processor_array")),
        sa.CheckConstraint("input_usd_per_million >= 0 AND input_usd_per_million < 1000000 AND output_usd_per_million >= 0 AND output_usd_per_million < 1000000 AND fixed_usd >= 0 AND fixed_usd < 1000000", name=op.f("ck_provider_profiles_valid_prices")),
        sa.CheckConstraint("max_input_tokens BETWEEN 0 AND 1000000000 AND max_output_tokens BETWEEN 0 AND 1000000000 AND max_attempts BETWEEN 1 AND 10", name=op.f("ck_provider_profiles_valid_bounds")), schema="app")
    op.create_table("workspace_allowances",
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("app.workspaces.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("month", sa.Date(), primary_key=True), sa.Column("allowance_usd", sa.Numeric(), nullable=False),
        sa.CheckConstraint("extract(day FROM month)=1", name=op.f("ck_workspace_allowances_month_start")),
        sa.CheckConstraint("allowance_usd >= 0 AND allowance_usd <= 20", name=op.f("ck_workspace_allowances_valid_allowance")), schema="app")
    op.create_table("cost_reservations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("app.workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.UUID()), sa.Column("profile_id", sa.UUID(), sa.ForeignKey("app.provider_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_hash", sa.Text(), nullable=False), sa.Column("month", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False), sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("maximum_usd", sa.Numeric(28, 12), nullable=False), sa.Column("actual_usd", sa.Numeric(28, 12)),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'reserved'")),
        sa.Column("charged_usd", sa.Numeric(28, 12), sa.Computed("CASE WHEN status='metered' THEN actual_usd ELSE greatest(maximum_usd,coalesce(actual_usd,0)) END", persisted=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "operation_hash", name="uq_cost_reservations_operation"),
        sa.ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("operation_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_cost_reservations_valid_operation_hash")),
        sa.CheckConstraint("extract(day FROM month)=1", name=op.f("ck_cost_reservations_month_start")),
        sa.CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name=op.f("ck_cost_reservations_valid_tokens")),
        sa.CheckConstraint("maximum_usd >= 0 AND maximum_usd <= 1000000000000 AND (actual_usd IS NULL OR (actual_usd >= 0 AND actual_usd <= 1000000000000))", name=op.f("ck_cost_reservations_valid_cost")),
        sa.CheckConstraint("status IN ('reserved','uncertain','metered') AND (status<>'metered' OR actual_usd IS NOT NULL) AND (status<>'reserved' OR actual_usd IS NULL)", name=op.f("ck_cost_reservations_valid_status")), schema="app")
    op.create_index("ix_cost_reservations_month", "cost_reservations", ["month"], schema="app")
    op.create_index("ix_cost_reservations_workspace_month", "cost_reservations", ["workspace_id", "month"], schema="app")
    for table in ("workspace_allowances", "cost_reservations"):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime")
    op.execute("REVOKE ALL ON app.provider_profiles FROM PUBLIC,docweave_runtime")
    op.execute("GRANT SELECT ON app.provider_profiles TO docweave_runtime")
    op.execute("""CREATE FUNCTION app.budget_month(p_when timestamptz) RETURNS date LANGUAGE sql STABLE
        SET search_path=pg_catalog,app AS $$ SELECT date_trunc('month',p_when AT TIME ZONE 'Asia/Calcutta')::date $$""")
    op.execute("""CREATE FUNCTION app.lock_budget() RETURNS void LANGUAGE sql
        SET search_path=pg_catalog,app AS $$ SELECT pg_advisory_xact_lock(7302026) $$""")
    op.execute("""
        CREATE FUNCTION app.immutable_profile() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
        BEGIN
            IF TG_OP='DELETE' OR (NEW.id,NEW.created_at,NEW.provider,NEW.model,NEW.backend,NEW.role,NEW.processor_ids,
                NEW.input_usd_per_million,NEW.output_usd_per_million,NEW.fixed_usd,NEW.max_input_tokens,NEW.max_output_tokens,NEW.max_attempts)
                IS DISTINCT FROM (OLD.id,OLD.created_at,OLD.provider,OLD.model,OLD.backend,OLD.role,OLD.processor_ids,
                OLD.input_usd_per_million,OLD.output_usd_per_million,OLD.fixed_usd,OLD.max_input_tokens,OLD.max_output_tokens,OLD.max_attempts) THEN
                RAISE EXCEPTION 'Register a new profile version' USING ERRCODE='22023';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER immutable_profile BEFORE UPDATE OR DELETE ON app.provider_profiles FOR EACH ROW EXECUTE FUNCTION app.immutable_profile()")
    op.execute("""
        CREATE FUNCTION app.profile_disabled_reason(p_profile uuid) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT CASE WHEN NOT p.enabled THEN 'disabled'
                WHEN NOT p.pricing_verified OR p.input_usd_per_million IS NULL OR p.output_usd_per_million IS NULL OR p.fixed_usd IS NULL THEN 'pricing_unavailable'
                WHEN NOT p.capabilities_verified OR p.max_input_tokens IS NULL OR p.max_output_tokens IS NULL THEN 'capability_unverified'
                WHEN NOT p.account_verified THEN 'account_unverified'
                WHEN jsonb_array_length(p.processor_ids)=0 OR EXISTS (SELECT 1 FROM jsonb_array_elements(p.processor_ids) v WHERE jsonb_typeof(v)<>'string')
                    OR (SELECT count(DISTINCT v) FROM jsonb_array_elements_text(p.processor_ids) v)<>jsonb_array_length(p.processor_ids)
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(p.processor_ids) v(id) LEFT JOIN app.processors pr ON pr.id=v.id WHERE pr.id IS NULL OR NOT pr.enabled)
                    OR NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider=p.provider AND pr.backend=p.backend AND pr.roles ? p.role)
                    OR (p.role='generation' AND (NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider='gemini' AND pr.roles ? 'embedding')
                        OR NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider='gemini' AND pr.roles ? 'reranking'))) THEN 'processor_unavailable'
                ELSE NULL END FROM app.provider_profiles p WHERE p.id=p_profile
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.set_workspace_allowance(p_workspace uuid,p_month date,p_amount numeric) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE billing_month date;
        BEGIN
            PERFORM app.lock_budget();
            billing_month:=coalesce(p_month,app.budget_month(clock_timestamp()));
            IF extract(day FROM billing_month)<>1 OR p_amount IS NULL OR NOT (p_amount>=0 AND p_amount<=20) THEN RAISE EXCEPTION 'Invalid allowance' USING ERRCODE='22023'; END IF;
            INSERT INTO app.workspace_allowances(workspace_id,month,allowance_usd) VALUES (p_workspace,billing_month,p_amount)
                ON CONFLICT (workspace_id,month) DO UPDATE SET allowance_usd=excluded.allowance_usd;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.reservation_view(p_id uuid,p_created boolean) RETURNS jsonb LANGUAGE sql STABLE
        SET search_path=pg_catalog,app AS $$
            SELECT jsonb_build_object('id',r.id,'workspace_id',r.workspace_id,'actor_id',r.actor_id,'project_id',r.project_id,'profile_id',r.profile_id,
                'month',r.month,'maximum_usd',r.maximum_usd::text,'actual_usd',r.actual_usd::text,'charged_usd',r.charged_usd::text,'status',r.status,'created',p_created)
            FROM app.cost_reservations r WHERE r.id=p_id
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.reserve_cost(p_hash text,p_profile uuid,p_input integer,p_output integer,p_project uuid) RETURNS jsonb
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
    """)
    op.execute("""
        CREATE FUNCTION app.settle_cost(p_reservation uuid,p_actual numeric,p_uncertain boolean) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE reservation app.cost_reservations%ROWTYPE; actual numeric;
        BEGIN
            PERFORM app.lock_budget();
            SELECT * INTO reservation FROM app.cost_reservations r WHERE r.id=p_reservation
                AND r.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                AND r.actor_id=nullif(current_setting('docweave.actor_id',true),'')::uuid FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_uncertain IS NULL OR (NOT p_uncertain AND p_actual IS NULL) OR
                (p_actual IS NOT NULL AND NOT (p_actual>=0 AND p_actual<1000000000000)) THEN RAISE EXCEPTION 'Invalid settlement' USING ERRCODE='22023'; END IF;
            actual:=ceil(p_actual*1000000000000)/1000000000000;
            IF reservation.status='metered' THEN
                IF p_uncertain OR actual IS DISTINCT FROM reservation.actual_usd THEN RAISE EXCEPTION 'Settlement conflict' USING ERRCODE='DW015'; END IF;
                RETURN app.reservation_view(p_reservation,false);
            END IF;
            IF p_uncertain THEN actual:=greatest(reservation.actual_usd,actual); END IF;
            UPDATE app.cost_reservations SET actual_usd=actual,status=CASE WHEN p_uncertain THEN 'uncertain' ELSE 'metered' END WHERE id=p_reservation;
            IF actual>reservation.maximum_usd THEN UPDATE app.provider_profiles SET enabled=false WHERE id=reservation.profile_id; END IF;
            RETURN app.reservation_view(p_reservation,false);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.usage_report(p_month date,p_project uuid) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE workspace uuid:=nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            billing_month date:=coalesce(p_month,app.budget_month(statement_timestamp()));
            allowance numeric; workspace_used numeric; global_used numeric; metered numeric; reserved numeric; uncertain numeric; result jsonb; capacity text;
        BEGIN
            IF extract(day FROM billing_month)<>1 THEN RAISE EXCEPTION 'Invalid month' USING ERRCODE='22023'; END IF;
            IF NOT EXISTS (SELECT 1 FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid) OR
                (p_project IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app.projects WHERE id=p_project AND workspace_id=workspace)) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            SELECT a.allowance_usd INTO allowance FROM app.workspace_allowances a WHERE a.workspace_id=workspace AND a.month=billing_month;
            SELECT coalesce(sum(r.charged_usd),0) INTO workspace_used FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.month=billing_month;
            SELECT coalesce(sum(r.charged_usd),0) INTO global_used FROM app.cost_reservations r WHERE r.month=billing_month;
            SELECT coalesce(sum(r.charged_usd) FILTER (WHERE r.status='metered'),0),coalesce(sum(r.charged_usd) FILTER (WHERE r.status='reserved'),0),
                coalesce(sum(r.charged_usd) FILTER (WHERE r.status='uncertain'),0) INTO metered,reserved,uncertain
                FROM app.cost_reservations r WHERE r.workspace_id=workspace AND r.month=billing_month AND (p_project IS NULL OR r.project_id=p_project);
            capacity:=CASE WHEN allowance IS NULL THEN 'allowance_required' WHEN workspace_used>=allowance THEN 'workspace_limit'
                WHEN global_used>=20 THEN 'application_capacity_unavailable' ELSE 'available' END;
            result:=jsonb_build_object('workspace_id',workspace,'month',to_char(billing_month,'YYYY-MM'),'timezone','Asia/Calcutta',
                'metered_usd',metered::text,'reserved_usd',reserved::text,'retained_uncertain_usd',uncertain::text,'workspace_allowance_usd',allowance::text,'capacity_status',capacity);
            IF p_project IS NOT NULL THEN result:=result||jsonb_build_object('project_id',p_project); END IF;
            RETURN result;
        END $$
    """)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature not in PRIVATE:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime")


def downgrade():
    op.execute("DROP TRIGGER immutable_profile ON app.provider_profiles")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.drop_table("cost_reservations", schema="app")
    op.drop_table("workspace_allowances", schema="app")
    op.drop_table("provider_profiles", schema="app")
