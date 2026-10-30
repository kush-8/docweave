"""Narrow workspace operations without general runtime domain writes."""

from alembic import op

revision = "0003_workspaces"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], schema="app")
    op.execute("""
        CREATE FUNCTION app.create_workspace(p_name text)
        RETURNS TABLE(id uuid,name text,role text,created_at timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE
            actor uuid := nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace app.workspaces%ROWTYPE;
        BEGIN
            IF actor IS NULL THEN
                RAISE EXCEPTION 'Actor context required' USING ERRCODE='42501';
            END IF;
            INSERT INTO app.workspaces(name) VALUES (p_name) RETURNING * INTO workspace;
            INSERT INTO app.memberships(workspace_id,user_id,role) VALUES (workspace.id,actor,'owner');
            RETURN QUERY SELECT workspace.id,workspace.name,'owner'::text,workspace.created_at;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.list_workspaces(p_after timestamptz,p_after_id uuid,p_limit integer)
        RETURNS TABLE(id uuid,name text,role text,created_at timestamptz)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT w.id,w.name,m.role,w.created_at
            FROM app.workspaces w JOIN app.memberships m ON m.workspace_id=w.id
            WHERE m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
                AND (p_after IS NULL OR (w.created_at,w.id)>(p_after,p_after_id))
            ORDER BY w.created_at,w.id LIMIT greatest(1,least(p_limit,101));
        $$
    """)
    for signature in ("app.create_workspace(text)", "app.list_workspaces(timestamptz,uuid,integer)"):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime")


def downgrade():
    op.execute("DROP FUNCTION app.list_workspaces(timestamptz,uuid,integer)")
    op.execute("DROP FUNCTION app.create_workspace(text)")
    op.drop_index("ix_memberships_user_id", table_name="memberships", schema="app")
