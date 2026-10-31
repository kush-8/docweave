"""Add direct ownership without switching legacy authorization or deleting data."""

from alembic import op
import sqlalchemy as sa

revision = '0013_personal_ownership'
down_revision = '0012_public_pilot_budget'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('owner_user_id', sa.UUID(), nullable=True), schema='app')
    op.create_foreign_key('fk_projects_owner_user_id_users', 'projects', 'users', ['owner_user_id'], ['id'], source_schema='app', referent_schema='app', ondelete='RESTRICT')
    op.create_index('ix_projects_owner_user_id', 'projects', ['owner_user_id'], schema='app')
    op.add_column('projects', sa.Column('repository_id', sa.BigInteger(), nullable=True), schema='app')
    op.add_column('projects', sa.Column('repository_branch', sa.Text(), nullable=True), schema='app')
    op.add_column('projects', sa.Column('application_path', sa.Text(), nullable=True), schema='app')
    op.add_column('projects', sa.Column('last_commit_sha', sa.Text(), nullable=True), schema='app')
    op.add_column('projects', sa.Column('stack_fingerprint', sa.Text(), nullable=True), schema='app')
    op.add_column('projects', sa.Column('sync_status', sa.Text(), nullable=False, server_default=sa.text("'repository_required'")), schema='app')
    op.create_check_constraint(op.f('ck_projects_positive_repository_id'), 'projects', 'repository_id > 0', schema='app')
    # Freeze membership writes until the sole-owner snapshot has been assigned.
    op.execute('LOCK TABLE app.memberships IN SHARE MODE')
    op.execute('''
        UPDATE app.projects p SET owner_user_id=m.user_id
        FROM app.memberships m
        WHERE m.workspace_id=p.workspace_id AND m.role='owner'
            AND p.owner_user_id IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM app.memberships other
                WHERE other.workspace_id=m.workspace_id AND other.role='owner'
                    AND other.user_id<>m.user_id
            )
    ''')
    op.execute('''
        CREATE FUNCTION app.personal_project_owned(p_project uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT EXISTS (
                SELECT 1 FROM app.projects p
                WHERE p.id=p_project
                    AND p.owner_user_id=nullif(current_setting('docweave.actor_id',true),'')::uuid
            )
        $$
    ''')
    op.execute('REVOKE ALL ON FUNCTION app.personal_project_owned(uuid) FROM PUBLIC,docweave_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_project_owned(uuid) TO docweave_runtime')
    # Authorization cutover is a separate migration after descendant scope checks.


def downgrade():
    op.execute('DROP FUNCTION app.personal_project_owned(uuid)')
    op.drop_constraint(op.f('ck_projects_positive_repository_id'), 'projects', schema='app', type_='check')
    op.drop_column('projects', 'sync_status', schema='app')
    op.drop_column('projects', 'stack_fingerprint', schema='app')
    op.drop_column('projects', 'last_commit_sha', schema='app')
    op.drop_column('projects', 'application_path', schema='app')
    op.drop_column('projects', 'repository_branch', schema='app')
    op.drop_column('projects', 'repository_id', schema='app')
    op.drop_index('ix_projects_owner_user_id', table_name='projects', schema='app')
    op.drop_constraint('fk_projects_owner_user_id_users', 'projects', schema='app', type_='foreignkey')
    op.drop_column('projects', 'owner_user_id', schema='app')
