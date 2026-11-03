"""Bind committed erasure to external content-free deletion intents."""
from alembic import op

revision = '0042_deletion_receipts'
down_revision = '0041_chat_cleanup'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE app.deletion_receipts (
        hash text CONSTRAINT pk_deletion_receipts PRIMARY KEY,
        CONSTRAINT ck_deletion_receipts_hash_format CHECK (hash ~ '^[0-9a-f]{64}$'))""")
    op.execute('REVOKE ALL ON app.deletion_receipts FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('GRANT SELECT,INSERT ON app.deletion_receipts TO docweave_runtime')
    op.execute('GRANT SELECT ON app.deletion_receipts TO docweave_worker')


def downgrade():
    op.execute('DROP TABLE app.deletion_receipts')
