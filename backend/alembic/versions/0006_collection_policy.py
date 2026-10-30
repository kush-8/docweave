"""Grant-aware collections and revisioned, scope-specific processor consent."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_collection_policy"
down_revision = "0005_projects"
branch_labels = None
depends_on = None

FUNCTIONS = ("app.immutable_processor()", "app.reconcile_member_grants()", "app.collection_can(uuid,text)",
    "app.collection_workspace(uuid)", "app.create_collection(uuid,text)", "app.collection_grants(uuid)",
    "app.replace_collection_grants(uuid,integer,jsonb)", "app.processing_policy(text,uuid)",
    "app.replace_processing_policy(text,uuid,integer,jsonb)")


def upgrade():
    for table, column in (("projects", "processing_revision"), ("collections", "grant_revision"), ("collections", "processing_revision")):
        op.add_column(table, sa.Column(column, sa.Integer(), nullable=False, server_default=sa.text("1")), schema="app")
        op.create_check_constraint(op.f(f"ck_{table}_positive_{column}"), table, f"{column} >= 1", schema="app")
    op.create_unique_constraint("uq_collections_id_workspace_id", "collections", ["id", "workspace_id"], schema="app")
    op.create_table("collection_grants",
        sa.Column("collection_id", sa.UUID(), primary_key=True), sa.Column("user_id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False), sa.Column("access", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id", "user_id"], ["app.memberships.workspace_id", "app.memberships.user_id"], ondelete="CASCADE"),
        sa.CheckConstraint("access IN ('read','write')", name=op.f("ck_collection_grants_valid_access")), schema="app")
    op.create_index("ix_collection_grants_membership", "collection_grants", ["workspace_id", "user_id"], schema="app")
    op.create_table("processors",
        sa.Column("id", sa.Text(), primary_key=True), sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("backend", sa.Text(), nullable=False), sa.Column("roles", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint("id ~ '[^[:space:]]' AND backend ~ '[^[:space:]]'", name=op.f("ck_processors_nonblank_identity")),
        sa.CheckConstraint("provider IN ('gemini','groq','huggingface')", name=op.f("ck_processors_valid_provider")),
        sa.CheckConstraint("jsonb_typeof(roles)='array' AND jsonb_array_length(roles)>0 AND roles <@ '[\"embedding\",\"reranking\",\"query_resolution\",\"summarization\",\"generation\"]'::jsonb", name=op.f("ck_processors_valid_roles")), schema="app")
    for kind, parent in (("project", "projects"), ("collection", "collections")):
        op.create_table(f"{kind}_processor_approvals",
            sa.Column(f"{kind}_id", sa.UUID(), primary_key=True),
            sa.Column("processor_id", sa.Text(), sa.ForeignKey("app.processors.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("workspace_id", sa.UUID(), nullable=False),
            sa.Column("approved_by", sa.UUID(), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint([f"{kind}_id", "workspace_id"], [f"app.{parent}.id", f"app.{parent}.workspace_id"], ondelete="RESTRICT"), schema="app")
    for table in ("collection_grants", "project_processor_approvals", "collection_processor_approvals"):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime")
    op.execute("REVOKE ALL ON app.processors FROM PUBLIC,docweave_runtime")
    op.execute("GRANT SELECT ON app.processors TO docweave_runtime")
    op.execute("""
        CREATE FUNCTION app.immutable_processor() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
        BEGIN
            IF TG_OP='DELETE' OR (NEW.id,NEW.provider,NEW.backend,NEW.roles) IS DISTINCT FROM (OLD.id,OLD.provider,OLD.backend,OLD.roles) THEN
                RAISE EXCEPTION 'Processor identity is immutable; disable it and register a new ID' USING ERRCODE='22023';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER immutable_processor BEFORE UPDATE OR DELETE ON app.processors FOR EACH ROW EXECUTE FUNCTION app.immutable_processor()")
    op.execute("""
        CREATE FUNCTION app.reconcile_member_grants() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
        BEGIN
            IF TG_OP='DELETE' THEN
                WITH changed AS (
                    DELETE FROM app.collection_grants WHERE workspace_id=OLD.workspace_id AND user_id=OLD.user_id RETURNING collection_id
                ) UPDATE app.collections SET grant_revision=grant_revision+1 WHERE id IN (SELECT collection_id FROM changed);
                RETURN OLD;
            END IF;
            IF NEW.role='member' AND OLD.role<>'member' THEN
                WITH changed AS (
                    UPDATE app.collection_grants SET access='read' WHERE workspace_id=OLD.workspace_id AND user_id=OLD.user_id AND access='write' RETURNING collection_id
                ) UPDATE app.collections SET grant_revision=grant_revision+1 WHERE id IN (SELECT collection_id FROM changed);
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER reconcile_member_grants BEFORE UPDATE OF role OR DELETE ON app.memberships FOR EACH ROW EXECUTE FUNCTION app.reconcile_member_grants()")
    op.execute("""
        CREATE FUNCTION app.collection_can(p_collection uuid,p_action text) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT EXISTS (SELECT 1 FROM app.collections c JOIN app.memberships m ON m.workspace_id=c.workspace_id
                WHERE c.id=p_collection AND c.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid AND (
                    (m.role='owner' AND p_action IN ('read','write','manage')) OR
                    (p_action='read' AND EXISTS (SELECT 1 FROM app.collection_grants g WHERE g.collection_id=c.id AND g.user_id=m.user_id)) OR
                    (p_action='write' AND m.role='maintainer' AND EXISTS (SELECT 1 FROM app.collection_grants g WHERE g.collection_id=c.id AND g.user_id=m.user_id AND g.access='write'))))
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.collection_workspace(p_collection uuid) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT c.workspace_id FROM app.collections c JOIN app.memberships m ON m.workspace_id=c.workspace_id
            WHERE c.id=p_collection AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
                AND (m.role='owner' OR EXISTS (SELECT 1 FROM app.collection_grants g WHERE g.collection_id=c.id AND g.user_id=m.user_id))
        $$
    """)
    op.execute("DROP POLICY runtime_read ON app.collections")
    op.execute("CREATE POLICY runtime_read ON app.collections FOR SELECT TO docweave_runtime USING (app.collection_can(id,'read'))")
    op.execute("""
        CREATE FUNCTION app.create_collection(p_project uuid,p_name text) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE collection app.collections%ROWTYPE;
        BEGIN
            PERFORM app.lock_workspace_owner();
            IF NOT EXISTS (SELECT 1 FROM app.projects WHERE id=p_project AND workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid) THEN
                RAISE EXCEPTION 'Not found' USING ERRCODE='P0002';
            END IF;
            INSERT INTO app.collections(workspace_id,project_id,name) VALUES (nullif(current_setting('docweave.workspace_id',true),'')::uuid,p_project,p_name) RETURNING * INTO collection;
            RETURN jsonb_build_object('id',collection.id,'project_id',collection.project_id,'name',collection.name,'can_write',true);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.collection_grants(p_collection uuid) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE revision integer; grants jsonb;
        BEGIN
            PERFORM app.lock_workspace_owner();
            SELECT c.grant_revision INTO revision FROM app.collections c WHERE c.id=p_collection
                AND c.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            SELECT coalesce(jsonb_agg(jsonb_build_object('user_id',g.user_id,'access',g.access) ORDER BY g.user_id),'[]'::jsonb)
                INTO grants FROM app.collection_grants g WHERE g.collection_id=p_collection;
            RETURN jsonb_build_object('revision',revision,'grants',grants);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.replace_collection_grants(p_collection uuid,p_revision integer,p_grants jsonb) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE revision integer; workspace uuid := nullif(current_setting('docweave.workspace_id',true),'')::uuid;
        BEGIN
            PERFORM app.lock_workspace_owner();
            SELECT c.grant_revision INTO revision FROM app.collections c WHERE c.id=p_collection AND c.workspace_id=workspace FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_revision IS DISTINCT FROM revision THEN RAISE EXCEPTION 'Stale revision' USING ERRCODE='DW003'; END IF;
            IF jsonb_typeof(p_grants) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid grants' USING ERRCODE='22023'; END IF;
            IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_grants) g GROUP BY (g->>'user_id')::uuid HAVING count(*)>1) OR
                EXISTS (SELECT 1 FROM jsonb_array_elements(p_grants) g LEFT JOIN app.memberships m ON m.workspace_id=workspace AND m.user_id=(g->>'user_id')::uuid
                    WHERE m.user_id IS NULL OR g->>'access' IS NULL OR g->>'access' NOT IN ('read','write') OR (g->>'access'='write' AND m.role NOT IN ('owner','maintainer'))) THEN
                RAISE EXCEPTION 'Invalid grants' USING ERRCODE='22023';
            END IF;
            DELETE FROM app.collection_grants WHERE collection_id=p_collection;
            INSERT INTO app.collection_grants(collection_id,workspace_id,user_id,access)
                SELECT p_collection,workspace,(g->>'user_id')::uuid,g->>'access' FROM jsonb_array_elements(p_grants) g;
            UPDATE app.collections SET grant_revision=grant_revision+1 WHERE id=p_collection;
            RETURN app.collection_grants(p_collection);
        END $$
    """)
    # Authorization, revision and IDs must share a snapshot even when an inner read waits.
    op.execute("""
        CREATE FUNCTION app.processing_policy(p_kind text,p_resource uuid) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE revision integer; processors jsonb;
        BEGIN
            IF p_kind='project' THEN
                SELECT p.processing_revision INTO revision FROM app.projects p WHERE p.id=p_resource
                    AND p.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                    AND EXISTS (SELECT 1 FROM app.memberships m WHERE m.workspace_id=p.workspace_id AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid);
                IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
                SELECT coalesce(jsonb_agg(a.processor_id ORDER BY a.processor_id),'[]'::jsonb) INTO processors FROM app.project_processor_approvals a WHERE a.project_id=p_resource;
            ELSIF p_kind='collection' THEN
                IF NOT app.collection_can(p_resource,'read') THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
                SELECT c.processing_revision INTO revision FROM app.collections c WHERE c.id=p_resource;
                SELECT coalesce(jsonb_agg(a.processor_id ORDER BY a.processor_id),'[]'::jsonb) INTO processors FROM app.collection_processor_approvals a WHERE a.collection_id=p_resource;
            ELSE
                RAISE EXCEPTION 'Invalid scope' USING ERRCODE='22023';
            END IF;
            RETURN jsonb_build_object('revision',revision,'approved_processor_ids',processors);
        END $$
    """)
    op.execute("""
        CREATE FUNCTION app.replace_processing_policy(p_kind text,p_resource uuid,p_revision integer,p_processors jsonb) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE revision integer; workspace uuid := nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            actor uuid := nullif(current_setting('docweave.actor_id',true),'')::uuid;
        BEGIN
            PERFORM app.lock_workspace_owner();
            IF p_kind='project' THEN
                SELECT p.processing_revision INTO revision FROM app.projects p WHERE p.id=p_resource AND p.workspace_id=workspace FOR UPDATE;
            ELSIF p_kind='collection' THEN
                SELECT c.processing_revision INTO revision FROM app.collections c WHERE c.id=p_resource AND c.workspace_id=workspace FOR UPDATE;
            ELSE
                RAISE EXCEPTION 'Invalid scope' USING ERRCODE='22023';
            END IF;
            IF revision IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_revision IS DISTINCT FROM revision THEN RAISE EXCEPTION 'Stale revision' USING ERRCODE='DW003'; END IF;
            IF jsonb_typeof(p_processors) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid processors' USING ERRCODE='22023'; END IF;
            IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_processors) v WHERE jsonb_typeof(v)<>'string') OR
                EXISTS (SELECT 1 FROM jsonb_array_elements_text(p_processors) v GROUP BY v HAVING count(*)>1) THEN
                RAISE EXCEPTION 'Invalid processors' USING ERRCODE='22023';
            END IF;
            PERFORM p.id FROM app.processors p WHERE p.id IN (SELECT jsonb_array_elements_text(p_processors)) ORDER BY p.id FOR SHARE;
            IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(p_processors) wanted(id) LEFT JOIN app.processors p ON p.id=wanted.id WHERE p.id IS NULL OR NOT p.enabled) THEN
                RAISE EXCEPTION 'Invalid processors' USING ERRCODE='22023';
            END IF;
            IF p_kind='project' THEN
                DELETE FROM app.project_processor_approvals WHERE project_id=p_resource;
                INSERT INTO app.project_processor_approvals(project_id,workspace_id,processor_id,approved_by)
                    SELECT p_resource,workspace,v,actor FROM jsonb_array_elements_text(p_processors) v;
                UPDATE app.projects SET processing_revision=processing_revision+1 WHERE id=p_resource;
            ELSE
                DELETE FROM app.collection_processor_approvals WHERE collection_id=p_resource;
                INSERT INTO app.collection_processor_approvals(collection_id,workspace_id,processor_id,approved_by)
                    SELECT p_resource,workspace,v,actor FROM jsonb_array_elements_text(p_processors) v;
                UPDATE app.collections SET processing_revision=processing_revision+1 WHERE id=p_resource;
            END IF;
            RETURN app.processing_policy(p_kind,p_resource);
        END $$
    """)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature not in FUNCTIONS[:2]:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime")


def downgrade():
    op.execute("DROP TRIGGER reconcile_member_grants ON app.memberships")
    op.execute("DROP TRIGGER immutable_processor ON app.processors")
    op.execute("DROP POLICY runtime_read ON app.collections")
    op.execute("""
        CREATE POLICY runtime_read ON app.collections FOR SELECT TO docweave_runtime USING (
            workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid AND EXISTS (
                SELECT 1 FROM app.memberships m WHERE m.workspace_id=collections.workspace_id
                AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid AND m.role='owner'))
    """)
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for table in ("collection_processor_approvals", "project_processor_approvals", "collection_grants", "processors"):
        op.drop_table(table, schema="app")
    op.drop_constraint("uq_collections_id_workspace_id", "collections", schema="app", type_="unique")
    for table, column in (("collections", "processing_revision"), ("collections", "grant_revision"), ("projects", "processing_revision")):
        op.drop_constraint(op.f(f"ck_{table}_positive_{column}"), table, schema="app", type_="check")
        op.drop_column(table, column, schema="app")
