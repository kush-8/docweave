"""Serialized owner-managed membership changes and recipient-bound invitations."""

from alembic import op
import sqlalchemy as sa

revision = "0004_memberships"
down_revision = "0003_workspaces"
branch_labels = None
depends_on = None

FUNCTIONS = (
    "app.lock_workspace_owner()",
    "app.list_members(timestamptz,uuid,integer)",
    "app.change_member(uuid,text)",
    "app.create_invitation(text,text,text)",
    "app.list_invitations(timestamptz,uuid,integer)",
    "app.revoke_invitation(uuid)",
    "app.accept_invitation(text)",
)


def upgrade():
    op.create_table("invitations",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("app.workspaces.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        sa.CheckConstraint("role IN ('owner','maintainer','member')", name=op.f("ck_invitations_valid_role")),
        sa.CheckConstraint("email ~ '[^[:space:]]'", name=op.f("ck_invitations_nonblank_email")),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_invitations_valid_token_hash")),
        sa.CheckConstraint("NOT (consumed_at IS NOT NULL AND revoked_at IS NOT NULL)", name=op.f("ck_invitations_one_terminal_state")),
        schema="app")
    op.execute("ALTER TABLE app.invitations ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON app.invitations FROM PUBLIC,docweave_runtime")
    op.execute("""
        CREATE FUNCTION app.lock_workspace_owner() RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE
            actor uuid := nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace uuid := nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            actor_role text;
        BEGIN
            PERFORM 1 FROM app.workspaces WHERE id=workspace FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            SELECT m.role INTO actor_role FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=actor;
            IF actor_role IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF actor_role<>'owner' THEN RAISE EXCEPTION 'Forbidden' USING ERRCODE='42501'; END IF;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.list_members(p_after timestamptz,p_after_id uuid,p_limit integer)
        RETURNS TABLE(workspace_id uuid,user_id uuid,role text,display_name text,id uuid,created_at timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        BEGIN
            PERFORM app.lock_workspace_owner();
            RETURN QUERY SELECT m.workspace_id,m.user_id,m.role,u.display_name,m.user_id,m.created_at
            FROM app.memberships m JOIN app.users u ON u.id=m.user_id
            WHERE m.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                AND (p_after IS NULL OR (m.created_at,m.user_id)>(p_after,p_after_id))
            ORDER BY m.created_at,m.user_id LIMIT greatest(1,least(p_limit,101));
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.change_member(p_user uuid,p_role text)
        RETURNS TABLE(workspace_id uuid,user_id uuid,role text,display_name text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE
            workspace uuid := nullif(current_setting('docweave.workspace_id',true),'')::uuid;
            previous_role text;
        BEGIN
            PERFORM app.lock_workspace_owner();
            IF p_role IS NOT NULL AND p_role NOT IN ('owner','maintainer','member') THEN
                RAISE EXCEPTION 'Invalid role' USING ERRCODE='22023';
            END IF;
            SELECT m.role INTO previous_role FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=p_user;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF previous_role='owner' AND (p_role IS NULL OR p_role<>'owner') AND
                (SELECT count(*) FROM app.memberships m WHERE m.workspace_id=workspace AND m.role='owner')<=1 THEN
                RAISE EXCEPTION 'Last owner' USING ERRCODE='DW001';
            END IF;
            IF p_role IS NULL THEN
                DELETE FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=p_user;
            ELSE
                UPDATE app.memberships m SET role=p_role WHERE m.workspace_id=workspace AND m.user_id=p_user;
            END IF;
            IF previous_role='owner' AND (p_role IS NULL OR p_role<>'owner') THEN
                UPDATE app.invitations i SET revoked_at=clock_timestamp()
                WHERE i.workspace_id=workspace AND i.created_by=p_user AND i.consumed_at IS NULL
                    AND i.revoked_at IS NULL AND i.expires_at>clock_timestamp();
            END IF;
            RETURN QUERY SELECT workspace,p_user,coalesce(p_role,previous_role),u.display_name FROM app.users u WHERE u.id=p_user;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.create_invitation(p_email text,p_role text,p_hash text)
        RETURNS TABLE(id uuid,workspace_id uuid,email text,role text,expires_at timestamptz,status text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE invitation app.invitations%ROWTYPE; issued timestamptz;
        BEGIN
            PERFORM app.lock_workspace_owner();
            issued:=clock_timestamp();
            INSERT INTO app.invitations(workspace_id,created_by,email,role,token_hash,created_at,expires_at)
            VALUES (nullif(current_setting('docweave.workspace_id',true),'')::uuid,
                nullif(current_setting('docweave.actor_id',true),'')::uuid,lower(p_email),p_role,p_hash,issued,issued+interval '48 hours')
            RETURNING * INTO invitation;
            RETURN QUERY SELECT invitation.id,invitation.workspace_id,invitation.email,invitation.role,invitation.expires_at,'pending'::text;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.list_invitations(p_after timestamptz,p_after_id uuid,p_limit integer)
        RETURNS TABLE(id uuid,workspace_id uuid,email text,role text,expires_at timestamptz,status text,created_at timestamptz)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        BEGIN
            PERFORM app.lock_workspace_owner();
            RETURN QUERY SELECT i.id,i.workspace_id,i.email,i.role,i.expires_at,
                CASE WHEN i.consumed_at IS NOT NULL THEN 'accepted' WHEN i.revoked_at IS NOT NULL THEN 'revoked'
                    WHEN i.expires_at<=clock_timestamp() THEN 'expired' ELSE 'pending' END,i.created_at
            FROM app.invitations i WHERE i.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid
                AND (p_after IS NULL OR (i.created_at,i.id)>(p_after,p_after_id))
            ORDER BY i.created_at,i.id LIMIT greatest(1,least(p_limit,101));
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.revoke_invitation(p_id uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        BEGIN
            PERFORM app.lock_workspace_owner();
            UPDATE app.invitations i SET revoked_at=coalesce(i.revoked_at,clock_timestamp())
            WHERE i.id=p_id AND i.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid AND i.consumed_at IS NULL;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION app.accept_invitation(p_hash text)
        RETURNS TABLE(workspace_id uuid,user_id uuid,role text,display_name text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
        DECLARE
            actor uuid := nullif(current_setting('docweave.actor_id',true),'')::uuid;
            workspace uuid;
            invitation app.invitations%ROWTYPE;
            recipient text;
            recipient_name text;
        BEGIN
            SELECT i.workspace_id INTO workspace FROM app.invitations i WHERE i.token_hash=p_hash;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            PERFORM 1 FROM app.workspaces w WHERE w.id=workspace FOR UPDATE;
            SELECT * INTO invitation FROM app.invitations i WHERE i.token_hash=p_hash
                AND i.consumed_at IS NULL AND i.revoked_at IS NULL AND i.expires_at>clock_timestamp() FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            SELECT u.email,u.display_name INTO recipient,recipient_name FROM app.users u WHERE u.id=actor AND u.email_verified;
            IF NOT FOUND OR lower(recipient) IS DISTINCT FROM invitation.email OR NOT EXISTS (
                SELECT 1 FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=invitation.created_by AND m.role='owner'
            ) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
            IF EXISTS (SELECT 1 FROM app.memberships m WHERE m.workspace_id=workspace AND m.user_id=actor) THEN
                RAISE EXCEPTION 'Already a member' USING ERRCODE='DW002';
            END IF;
            INSERT INTO app.memberships(workspace_id,user_id,role,created_at) VALUES (workspace,actor,invitation.role,clock_timestamp());
            UPDATE app.invitations i SET consumed_at=clock_timestamp() WHERE i.id=invitation.id;
            RETURN QUERY SELECT workspace,actor,invitation.role,recipient_name;
        END
        $$
    """)
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature != "app.lock_workspace_owner()":
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime")


def downgrade():
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.drop_table("invitations", schema="app")
