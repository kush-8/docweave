"""Report private indexing jobs and admission waits without false progress."""
import importlib.util
from pathlib import Path
from alembic import op

revision='0037_private_source_states'
down_revision='0036_private_source_indexing'
branch_labels=None
depends_on=None


def original():
    spec=importlib.util.spec_from_file_location('private_source_states_base',Path(__file__).with_name('0034_private_source_review.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ENTRIES.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)


def upgrade():
    sql=original().replace(
        "WHEN j.status IN ('failed','cancelled') THEN 'failed'\n WHEN j.status IN ('queued','running') THEN 'processing'",
        "WHEN pi.status='completion_unknown' THEN 'completion_unknown'\n WHEN j.status IN ('failed','cancelled') OR pi.status='failed' THEN 'failed'")
    sql=sql.replace("WHEN d.active_version_id IS NOT NULL THEN 'capacity' ELSE 'missing' END,",
        "WHEN activity.value THEN 'processing'\n WHEN d.active_version_id IS NOT NULL THEN 'capacity' ELSE 'missing' END,")
    sql=sql.replace("'active_job',coalesce(j.status IN ('queued','running'),false),'progress',j.stage)",
        "'active_job',activity.value,'progress',CASE WHEN pi.status='completion_unknown' THEN 'Provider result uncertain; operator reconciliation is required. No automatic replay.' WHEN pi.status IN ('queued','running') AND activity.value THEN 'Building private documentation index' ELSE j.stage END)")
    sql=sql.replace("LEFT JOIN LATERAL(SELECT jobs.status,jobs.stage", "LEFT JOIN app.private_index_jobs pi ON pi.document_id=d.id AND pi.document_version_id=d.active_version_id AND pi.generation_id=p_generation\n LEFT JOIN LATERAL(SELECT jobs.status,jobs.stage,jobs.lease_until")
    sql=sql.replace("WHERE p.id=p_project AND ds.active AND ds.approved_stack=dep;", """CROSS JOIN LATERAL(SELECT
 (coalesce(j.status='queued' OR j.status='running' AND j.lease_until>now(),false)
 OR coalesce(pi.status='queued' OR pi.status='running' AND pi.lease_expires_at>now(),false))
 AND EXISTS(SELECT 1 FROM app.index_generations WHERE id=p_generation AND enabled)
 AND app.personal_index_policy(c.id,p_generation) value) activity
 WHERE p.id=p_project AND ds.active AND ds.approved_stack=dep;""")
    op.execute(sql)


def downgrade():
    op.execute(original())
