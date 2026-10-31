"""Allow matching owner-only source scopes without a workspace."""
import importlib.util
from pathlib import Path
from alembic import op

revision = '0027_personal_source_scope'
down_revision = '0026_waiting_turn_resume'
branch_labels = None
depends_on = None


def definition():
    path = Path(__file__).with_name('0009_retrieval.py')
    spec = importlib.util.spec_from_file_location('source_scope_base', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FUNCTIONS['app.index_source_current(uuid)'].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)


def upgrade():
    op.execute(definition().replace('ds.workspace_id=p.workspace_id', 'ds.workspace_id IS NOT DISTINCT FROM p.workspace_id'))


def downgrade():
    op.execute(definition())
