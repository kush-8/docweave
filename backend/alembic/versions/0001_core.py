"""Core records and read-only tenant isolation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def record_columns():
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.create_table("users", *record_columns(),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        sa.CheckConstraint("issuer ~ '[^[:space:]]'", name=op.f("ck_users_nonblank_issuer")),
        sa.CheckConstraint("subject ~ '[^[:space:]]'", name=op.f("ck_users_nonblank_subject")),
        sa.CheckConstraint("display_name ~ '[^[:space:]]'", name=op.f("ck_users_nonblank_display_name")), schema="app")
    op.create_table("workspaces", *record_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name=op.f("ck_workspaces_nonblank_name")), schema="app")
    op.create_table("memberships",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "user_id", name="pk_memberships"),
        sa.ForeignKeyConstraint(["workspace_id"], ["app.workspaces.id"], ondelete="RESTRICT", name="fk_memberships_workspace_id_workspaces"),
        sa.ForeignKeyConstraint(["user_id"], ["app.users.id"], ondelete="RESTRICT", name="fk_memberships_user_id_users"),
        sa.CheckConstraint("role IN ('owner','maintainer','member')", name=op.f("ck_memberships_valid_role")), schema="app")
    op.create_table("projects", *record_columns(),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("stack", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("context_revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("architecture_notes", sa.Text(), nullable=True),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(["workspace_id"], ["app.workspaces.id"], ondelete="RESTRICT", name="fk_projects_workspace_id_workspaces"),
        sa.CheckConstraint("name ~ '[^[:space:]]'", name=op.f("ck_projects_nonblank_name")),
        sa.CheckConstraint("goal ~ '[^[:space:]]'", name=op.f("ck_projects_nonblank_goal")),
        sa.CheckConstraint("context_revision >= 1", name=op.f("ck_projects_positive_context_revision")),
        sa.CheckConstraint("jsonb_typeof(stack) = 'array'", name=op.f("ck_projects_stack_array")), schema="app")
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"], schema="app")

    actor = "nullif(current_setting('docweave.actor_id', true), '')::uuid"
    workspace = "nullif(current_setting('docweave.workspace_id', true), '')::uuid"
    member = f"EXISTS (SELECT 1 FROM app.memberships m WHERE m.user_id={actor} AND m.workspace_id={workspace})"
    predicates = {
        "memberships": f"user_id={actor} AND workspace_id={workspace}",
        "users": f"id={actor} AND {member}",
        "workspaces": f"id={workspace} AND {member}",
        "projects": f"workspace_id={workspace} AND {member}",
    }
    for table, predicate in predicates.items():
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY runtime_read ON app.{table} FOR SELECT TO docweave_runtime USING ({predicate})")
        op.execute(f"GRANT SELECT ON app.{table} TO docweave_runtime")


def downgrade():
    # Policies reference memberships, so remove them before their dependency table.
    for table in ("projects", "memberships", "workspaces", "users"):
        op.execute(f"DROP POLICY runtime_read ON app.{table}")
    for table in ("projects", "memberships", "workspaces", "users"):
        op.drop_table(table, schema="app")
