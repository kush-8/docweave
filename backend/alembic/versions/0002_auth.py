"""Expiring authentication records and narrowly scoped identity provisioning."""

from alembic import op
import sqlalchemy as sa

revision = "0002_auth"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("auth_flows",
        sa.Column("state_hash", sa.Text(), primary_key=True),
        sa.Column("browser_hash", sa.Text(), nullable=False, index=True),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True), schema="app")
    op.create_table("auth_sessions",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True), schema="app")
    op.create_table("auth_rate_limits",
        sa.Column("bucket", sa.Text(), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("resets_at", sa.DateTime(timezone=True), nullable=False), schema="app")
    for table in ("auth_flows", "auth_sessions", "auth_rate_limits"):
        op.execute(f"REVOKE ALL ON app.{table} FROM PUBLIC")
        op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON app.{table} TO docweave_runtime")
    # New users need their identity before they have a workspace membership.
    op.execute("ALTER POLICY runtime_read ON app.users USING (id=nullif(current_setting('docweave.actor_id',true),'')::uuid)")
    op.execute("""
        CREATE FUNCTION app.provision_identity(p_issuer text,p_subject text,p_name text,p_email text) RETURNS uuid
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            INSERT INTO app.users(issuer,subject,display_name,email,email_verified)
            VALUES (p_issuer,p_subject,p_name,p_email,true)
            ON CONFLICT (issuer,subject) DO UPDATE SET display_name=EXCLUDED.display_name,
                email=EXCLUDED.email,email_verified=true RETURNING id;
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION app.provision_identity(text,text,text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.provision_identity(text,text,text,text) TO docweave_runtime")


def downgrade():
    op.execute("DROP FUNCTION app.provision_identity(text,text,text,text)")
    op.execute("""ALTER POLICY runtime_read ON app.users USING (
        id=nullif(current_setting('docweave.actor_id',true),'')::uuid AND EXISTS (
            SELECT 1 FROM app.memberships m WHERE m.user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
            AND m.workspace_id=nullif(current_setting('docweave.workspace_id',true),'')::uuid))""")
    for table in ("auth_rate_limits", "auth_sessions", "auth_flows"):
        op.drop_table(table, schema="app")
