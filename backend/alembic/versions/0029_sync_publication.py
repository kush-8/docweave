"""Do not reconcile catalog selections from a rejected sync publication."""
from alembic import op
import sqlalchemy as sa

revision = '0029_sync_publication'
down_revision = '0028_sync_retries'
branch_labels = None
depends_on = None

BEFORE = 'RETURN true;'
AFTER = "RETURN job.kind<>'sync' OR p_result->>'status'<>'ready' OR (p_result->>'expected_revision')::integer=project.context_revision;"


def replace_result(before, after):
    definition = op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('app.personal_finish_job(uuid,uuid,jsonb)'::regprocedure)"))
    if before not in definition:
        raise ValueError('Unexpected sync publication function')
    op.execute(definition.replace(before, after))


def upgrade():
    replace_result(BEFORE, AFTER)


def downgrade():
    replace_result(AFTER, BEFORE)
