"""Manual context, owner-only default collections and durable pending documentation."""

from alembic import op
import sqlalchemy as sa

revision = "0005_projects"
down_revision = "0004_memberships"
branch_labels = None
depends_on = None

FUNCTIONS = ("app.project_workspace(uuid)", "app.project_view(uuid)",
    "app.replace_project_documentation(uuid)", "app.create_project(jsonb)", "app.update_project(uuid,integer,jsonb)")


def upgrade():
    # No previous runtime writer defined a dependency format; preserve legacy data for operator review.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM app.projects WHERE stack<>'[]'::jsonb) THEN
                RAISE EXCEPTION 'Nonempty legacy project stacks require operator review before migration' USING ERRCODE='22023';
            END IF;
        END $$
    """)
    op.create_unique_constraint("uq_projects_id_workspace_id", "projects", ["id", "workspace_id"], schema="app")
    op.create_table("collections",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("workspace_id", sa.UUID(), nullable=False, index=True),
        sa.Column("project_id", sa.UUID(), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name=op.f("ck_collections_nonblank_name")), schema="app")
    op.create_index("uq_collections_default_project", "collections", ["project_id"], unique=True,
        postgresql_where=sa.text("is_default"), schema="app")
    op.create_table("documentation_requests",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("workspace_id", sa.UUID(), nullable=False, index=True),
        sa.Column("project_id", sa.UUID(), nullable=False, index=True),
        sa.Column("requested_by", sa.UUID(), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("context_revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("state IN ('pending_review','superseded')", name=op.f("ck_documentation_requests_valid_state")),
        sa.CheckConstraint("context_revision >= 1", name=op.f("ck_documentation_requests_positive_context_revision")),
        sa.CheckConstraint("reason IN ('version_unresolved','source_catalog_unavailable')", name=op.f("ck_documentation_requests_valid_reason")), schema="app")
    for table in ("collections", "documentation_requests"):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime")
    op.execute("""
        CREATE POLICY runtime_read ON app.collections FOR SELECT TO docweave_runtime USING (
            workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid AND EXISTS (
                SELECT 1 FROM app.memberships m WHERE m.workspace_id=collections.workspace_id
                AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid AND m.role='owner'))
    """)
    op.execute("GRANT SELECT ON app.collections TO docweave_runtime")
    op.execute("INSERT INTO app.collections(project_id,workspace_id,name,is_default) SELECT id,workspace_id,'Default',true FROM app.projects")
    op.execute("""
        CREATE FUNCTION app.project_workspace(p_project uuid) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT p.workspace_id FROM app.projects p JOIN app.memberships m ON m.workspace_id=p.workspace_id
            WHERE p.id=p_project AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.project_view(p_project uuid) RETURNS jsonb
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT jsonb_build_object('id',p.id,'workspace_id',p.workspace_id,'name',p.name,'goal',p.goal,
                'stack',p.stack,'context_revision',p.context_revision,'default_collection_id',c.id,
                'source_state','pending_review','architecture_notes',coalesce(p.architecture_notes,''),
                'environment',coalesce(p.environment,''),'constraints',coalesce(p.constraints,''))
            FROM app.projects p JOIN app.collections c ON c.project_id=p.id AND c.is_default
            JOIN app.memberships m ON m.workspace_id=p.workspace_id
            WHERE p.id=p_project AND p.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                AND m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.replace_project_documentation(p_project uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        BEGIN
            UPDATE app.documentation_requests SET state='superseded' WHERE project_id=p_project AND state='pending_review';
            INSERT INTO app.documentation_requests(id,workspace_id,project_id,requested_by,context_revision,state,reason)
            SELECT (d->>'id')::uuid,p.workspace_id,p.id,nullif(current_setting('docweave.actor_id',true),'')::uuid,
                p.context_revision,'pending_review',CASE WHEN d->>'docs_target' IS NULL THEN 'version_unresolved' ELSE 'source_catalog_unavailable' END
            FROM app.projects p CROSS JOIN LATERAL jsonb_array_elements(p.stack) d WHERE p.id=p_project;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.create_project(p_context jsonb) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE project uuid;
        BEGIN
            PERFORM app.lock_workspace_owner();
            IF jsonb_typeof(p_context->'stack') IS DISTINCT FROM 'array' THEN
                RAISE EXCEPTION 'Invalid stack' USING ERRCODE='22023';
            END IF;
            IF jsonb_array_length(p_context->'stack')=0 THEN RAISE EXCEPTION 'Invalid stack' USING ERRCODE='22023'; END IF;
            INSERT INTO app.projects(workspace_id,name,goal,stack,architecture_notes,environment,constraints)
            VALUES (nullif(current_setting('docweave.workspace_id',true),'')::uuid,p_context->>'name',p_context->>'goal',
                p_context->'stack',p_context->>'architecture_notes',p_context->>'environment',p_context->>'constraints') RETURNING id INTO project;
            INSERT INTO app.collections(workspace_id,project_id,name,is_default)
            VALUES (nullif(current_setting('docweave.workspace_id',true),'')::uuid,project,'Default',true);
            PERFORM app.replace_project_documentation(project);
            RETURN app.project_view(project);
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.update_project(p_project uuid,p_revision integer,p_context jsonb) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE project app.projects%ROWTYPE;
        BEGIN
            PERFORM app.lock_workspace_owner();
            SELECT * INTO project FROM app.projects p WHERE p.id=p_project
                AND p.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF p_revision IS DISTINCT FROM project.context_revision THEN RAISE EXCEPTION 'Stale revision' USING ERRCODE='DW003'; END IF;
            IF p_context ? 'stack' THEN
                IF jsonb_typeof(p_context->'stack') IS DISTINCT FROM 'array' THEN
                    RAISE EXCEPTION 'Invalid stack' USING ERRCODE='22023';
                END IF;
                IF jsonb_array_length(p_context->'stack')=0 THEN RAISE EXCEPTION 'Invalid stack' USING ERRCODE='22023'; END IF;
            END IF;
            UPDATE app.projects SET name=coalesce(p_context->>'name',project.name),goal=coalesce(p_context->>'goal',project.goal),
                stack=coalesce(p_context->'stack',project.stack),context_revision=project.context_revision+1,
                architecture_notes=coalesce(p_context->>'architecture_notes',project.architecture_notes),
                environment=coalesce(p_context->>'environment',project.environment),constraints=coalesce(p_context->>'constraints',project.constraints)
            WHERE id=p_project;
            IF p_context ? 'stack' THEN
                PERFORM app.replace_project_documentation(p_project);
            ELSE
                UPDATE app.documentation_requests SET context_revision=project.context_revision+1 WHERE project_id=p_project AND state='pending_review';
            END IF;
            RETURN app.project_view(p_project);
        END
        $$
    """)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature != "app.replace_project_documentation(uuid)":
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime")


def downgrade():
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.drop_table("documentation_requests", schema="app")
    op.drop_table("collections", schema="app")
    op.drop_constraint("uq_projects_id_workspace_id", "projects", schema="app", type_="unique")
