"""Immutable public catalog definitions and explicit content scopes; no runtime cutover."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0014_public_catalog'
down_revision = '0013_personal_ownership'
branch_labels = None
depends_on = None

DESCENDANTS = ('sources', 'documents', 'document_versions', 'ingestion_jobs', 'document_indexes', 'chunks')
DIRECT = (
    ('collections', 'project_id', 'projects'),
    ('documentation_selections', 'project_id', 'projects'),
    ('sources', 'collection_id', 'collections'),
    ('documents', 'collection_id', 'collections'),
    ('document_versions', 'document_id', 'documents'),
    ('ingestion_jobs', 'document_id', 'documents'),
    ('document_indexes', 'document_id', 'documents'),
    ('chunks', 'collection_id', 'collections'),
    ('chunks', 'project_id', 'projects'),
    ('chunks', 'document_id', 'documents'),
)
SCOPED = ('collections', 'documentation_selections', *DESCENDANTS)


def record():
    return [sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.alter_column('projects', 'workspace_id', nullable=True, schema='app')
    op.create_table('public_catalog_revisions', *record(),
        *(sa.Column(name, sa.Text(), nullable=False) for name in (
            'technology', 'ecosystem', 'docs_target', 'origin', 'path_prefix', 'source_url', 'attribution', 'source_hash')),
        sa.Column('coverage', JSONB(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source_approved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.CheckConstraint("technology ~ '[^[:space:]]' AND docs_target ~ '[^[:space:]]'", name=op.f('ck_public_catalog_revisions_nonblank_identity')),
        sa.CheckConstraint("ecosystem IN ('python','javascript')", name=op.f('ck_public_catalog_revisions_valid_ecosystem')),
        sa.CheckConstraint("jsonb_typeof(coverage)='object' AND coalesce(coverage->>'granularity','') IN ('exact','major','minor') AND jsonb_typeof(coverage->'version')='string' AND coalesce(coverage->>'version','') ~ '[^[:space:]]'", name=op.f('ck_public_catalog_revisions_valid_coverage')),
        sa.CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_public_catalog_revisions_valid_source_hash')),
        schema='app')
    op.create_table('project_catalog_selections', *record(),
        sa.Column('project_id', sa.UUID(), sa.ForeignKey('app.projects.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('dependency_id', sa.Text(), nullable=False),
        sa.Column('catalog_revision_id', sa.UUID(), sa.ForeignKey('app.public_catalog_revisions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fallback_accepted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.UniqueConstraint('project_id', 'dependency_id', name='uq_project_catalog_selections_dependency'),
        sa.CheckConstraint("dependency_id ~ '[^[:space:]]'", name=op.f('ck_project_catalog_selections_nonblank_dependency')),
        schema='app')
    for table in ('public_catalog_revisions', 'project_catalog_selections'):
        op.execute(f'ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime,docweave_worker')
        op.execute(f'GRANT SELECT ON app.{table} TO docweave_runtime')
    op.execute('CREATE POLICY runtime_read ON app.public_catalog_revisions FOR SELECT TO docweave_runtime USING (enabled AND source_approved)')
    op.execute('CREATE POLICY runtime_read ON app.project_catalog_selections FOR SELECT TO docweave_runtime USING (app.personal_project_owned(project_id))')
    for table in ('collections', 'documentation_selections'):
        op.add_column(table, sa.Column('catalog_revision_id', sa.UUID(), sa.ForeignKey('app.public_catalog_revisions.id', ondelete='RESTRICT'), nullable=True), schema='app')
        op.alter_column(table, 'project_id', nullable=True, schema='app')
        op.alter_column(table, 'workspace_id', nullable=True, schema='app')
        scope = '(project_id IS NOT NULL AND catalog_revision_id IS NULL) OR (project_id IS NULL AND workspace_id IS NULL AND catalog_revision_id IS NOT NULL'
        if table == 'documentation_selections':
            scope += ' AND approved_stack IS NULL'
        op.create_check_constraint(op.f(f'ck_{table}_exact_parent'), table, scope + ')', schema='app')
    for table in DESCENDANTS:
        op.alter_column(table, 'workspace_id', nullable=True, schema='app')
    op.alter_column('chunks', 'project_id', nullable=True, schema='app')
    for table, column, parent in DIRECT:
        op.create_foreign_key(f'fk_{table}_{column}_direct', table, parent, [column], ['id'], source_schema='app', referent_schema='app', ondelete='RESTRICT')
    op.create_foreign_key('fk_documents_active_version_id_document_versions', 'documents', 'document_versions', ['active_version_id'], ['id'], source_schema='app', referent_schema='app', ondelete='RESTRICT')
    op.execute(IMMUTABLE)
    op.execute(SCOPE_GUARD)
    op.execute('REVOKE ALL ON FUNCTION app.immutable_catalog_revision(),app.enforce_catalog_scope() FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('CREATE TRIGGER immutable_catalog_revision BEFORE UPDATE OR DELETE ON app.public_catalog_revisions FOR EACH ROW EXECUTE FUNCTION app.immutable_catalog_revision()')
    for table in SCOPED:
        op.execute(f'CREATE TRIGGER enforce_catalog_scope BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.enforce_catalog_scope()')
    op.execute(PREFLIGHT)


IMMUTABLE = '''
CREATE FUNCTION app.immutable_catalog_revision() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
BEGIN
    IF TG_OP='DELETE'
        OR (to_jsonb(NEW)-'enabled'-'source_approved') IS DISTINCT FROM (to_jsonb(OLD)-'enabled'-'source_approved')
        OR (NEW.enabled AND NOT OLD.enabled)
        OR (NEW.source_approved AND NOT OLD.source_approved) THEN
        RAISE EXCEPTION 'Catalog revision is immutable; create a replacement revision' USING ERRCODE='22023';
    END IF;
    RETURN NEW;
END $$
'''

SCOPE_GUARD = '''
CREATE FUNCTION app.enforce_catalog_scope() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
DECLARE c app.collections%ROWTYPE; d app.documents%ROWTYPE; s app.sources%ROWTYPE;
    selection app.documentation_selections%ROWTYPE; revision app.public_catalog_revisions%ROWTYPE; p app.projects%ROWTYPE;
BEGIN
    IF TG_OP='UPDATE' AND (
        to_jsonb(NEW)->'workspace_id',to_jsonb(NEW)->'project_id',to_jsonb(NEW)->'collection_id',
        to_jsonb(NEW)->'document_id',to_jsonb(NEW)->'source_id',to_jsonb(NEW)->'source_selection_id',to_jsonb(NEW)->'catalog_revision_id'
    ) IS DISTINCT FROM (
        to_jsonb(OLD)->'workspace_id',to_jsonb(OLD)->'project_id',to_jsonb(OLD)->'collection_id',
        to_jsonb(OLD)->'document_id',to_jsonb(OLD)->'source_id',to_jsonb(OLD)->'source_selection_id',to_jsonb(OLD)->'catalog_revision_id'
    ) THEN
        RAISE EXCEPTION 'Content scope is immutable' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='collections' THEN
        IF NEW.project_id IS NOT NULL THEN
            SELECT * INTO p FROM app.projects WHERE id=NEW.project_id;
            IF p.id IS NULL OR NEW.workspace_id IS DISTINCT FROM p.workspace_id THEN
                RAISE EXCEPTION 'Collection project scope mismatch' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    ELSIF TG_TABLE_NAME='documentation_selections' THEN
        IF NEW.project_id IS NOT NULL THEN
            SELECT * INTO p FROM app.projects WHERE id=NEW.project_id;
            IF p.id IS NULL OR NEW.workspace_id IS DISTINCT FROM p.workspace_id THEN
                RAISE EXCEPTION 'Selection project scope mismatch' USING ERRCODE='23514';
            END IF;
        END IF;
        IF NEW.catalog_revision_id IS NOT NULL THEN
            SELECT * INTO revision FROM app.public_catalog_revisions WHERE id=NEW.catalog_revision_id;
            IF revision.id IS NULL OR (NEW.technology,NEW.docs_target,NEW.coverage,NEW.source_url,NEW.origin,NEW.path_prefix,NEW.attribution)
                IS DISTINCT FROM (revision.technology,revision.docs_target,revision.coverage,revision.source_url,revision.origin,revision.path_prefix,revision.attribution) THEN
                RAISE EXCEPTION 'Public selection must match immutable catalog provenance' USING ERRCODE='23514';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME='sources' THEN
        SELECT * INTO c FROM app.collections WHERE id=NEW.collection_id;
        SELECT * INTO selection FROM app.documentation_selections WHERE id=NEW.source_selection_id;
        IF c.id IS NULL OR selection.id IS NULL OR NEW.workspace_id IS DISTINCT FROM c.workspace_id
            OR (selection.workspace_id,selection.project_id,selection.catalog_revision_id)
                IS DISTINCT FROM (c.workspace_id,c.project_id,c.catalog_revision_id) THEN
            RAISE EXCEPTION 'Source scope mismatch' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='documents' THEN
        SELECT * INTO c FROM app.collections WHERE id=NEW.collection_id;
        IF c.id IS NULL OR NEW.workspace_id IS DISTINCT FROM c.workspace_id THEN
            RAISE EXCEPTION 'Document scope mismatch' USING ERRCODE='23514';
        END IF;
        IF NEW.source_id IS NOT NULL THEN
            SELECT * INTO s FROM app.sources WHERE id=NEW.source_id;
            IF s.id IS NULL OR s.collection_id<>NEW.collection_id OR s.workspace_id IS DISTINCT FROM NEW.workspace_id THEN
                RAISE EXCEPTION 'Document source mismatch' USING ERRCODE='23514';
            END IF;
        END IF;
        IF NEW.active_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM app.document_versions v WHERE v.id=NEW.active_version_id AND v.document_id=NEW.id
        ) THEN RAISE EXCEPTION 'Active version mismatch' USING ERRCODE='23514'; END IF;
    ELSE
        SELECT * INTO d FROM app.documents WHERE id=NEW.document_id;
        IF d.id IS NULL OR NEW.workspace_id IS DISTINCT FROM d.workspace_id THEN
            RAISE EXCEPTION 'Document descendant scope mismatch' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME IN ('document_indexes','chunks') THEN
            IF NOT EXISTS (
                SELECT 1 FROM app.document_versions v WHERE v.id=NEW.document_version_id AND v.document_id=NEW.document_id
            ) THEN RAISE EXCEPTION 'Indexed version mismatch' USING ERRCODE='23514'; END IF;
        END IF;
        IF TG_TABLE_NAME='chunks' THEN
            SELECT * INTO c FROM app.collections WHERE id=NEW.collection_id;
            IF c.id IS NULL OR d.collection_id<>NEW.collection_id OR NEW.project_id IS DISTINCT FROM c.project_id THEN
                RAISE EXCEPTION 'Chunk collection scope mismatch' USING ERRCODE='23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$
'''

PREFLIGHT = '''
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM app.sources s JOIN app.collections c ON c.id=s.collection_id
        JOIN app.documentation_selections selection ON selection.id=s.source_selection_id
        WHERE (s.workspace_id,selection.workspace_id,selection.project_id)
            IS DISTINCT FROM (c.workspace_id,c.workspace_id,c.project_id)
    ) OR EXISTS (
        SELECT 1 FROM app.documents d JOIN app.sources s ON s.id=d.source_id
        WHERE d.collection_id<>s.collection_id OR d.workspace_id IS DISTINCT FROM s.workspace_id
    ) OR EXISTS (
        SELECT 1 FROM app.documents d JOIN app.document_versions v ON v.id=d.active_version_id WHERE v.document_id<>d.id
    ) OR EXISTS (
        SELECT 1 FROM app.document_indexes i JOIN app.document_versions v ON v.id=i.document_version_id WHERE v.document_id<>i.document_id
    ) OR EXISTS (
        SELECT 1 FROM app.chunks ch JOIN app.document_versions v ON v.id=ch.document_version_id
        JOIN app.documents d ON d.id=ch.document_id JOIN app.collections c ON c.id=ch.collection_id
        WHERE v.document_id<>ch.document_id OR d.collection_id<>ch.collection_id OR ch.project_id IS DISTINCT FROM c.project_id
    ) THEN
        RAISE EXCEPTION 'Existing content has ambiguous scope; explicit operator reconciliation required' USING ERRCODE='23514';
    END IF;
END $$
'''


def downgrade():
    # Never delete public content merely to make the legacy nonnullable schema fit.
    op.execute('''DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM app.collections WHERE catalog_revision_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM app.documentation_selections WHERE catalog_revision_id IS NOT NULL)
            OR EXISTS (SELECT 1 FROM app.project_catalog_selections)
            OR EXISTS (SELECT 1 FROM app.public_catalog_revisions)
            OR EXISTS (SELECT 1 FROM app.projects WHERE workspace_id IS NULL) THEN
            RAISE EXCEPTION 'Catalog records require preservation before downgrade' USING ERRCODE='23514';
        END IF;
    END $$''')
    for table in SCOPED:
        op.execute(f'DROP TRIGGER enforce_catalog_scope ON app.{table}')
    op.execute('DROP TRIGGER immutable_catalog_revision ON app.public_catalog_revisions')
    op.execute('DROP FUNCTION app.enforce_catalog_scope(),app.immutable_catalog_revision()')
    op.drop_constraint('fk_documents_active_version_id_document_versions', 'documents', schema='app', type_='foreignkey')
    for table, column, _ in reversed(DIRECT):
        op.drop_constraint(f'fk_{table}_{column}_direct', table, schema='app', type_='foreignkey')
    op.alter_column('chunks', 'project_id', nullable=False, schema='app')
    for table in DESCENDANTS:
        op.alter_column(table, 'workspace_id', nullable=False, schema='app')
    for table in ('collections', 'documentation_selections'):
        op.drop_constraint(op.f(f'ck_{table}_exact_parent'), table, schema='app', type_='check')
        op.alter_column(table, 'workspace_id', nullable=False, schema='app')
        op.alter_column(table, 'project_id', nullable=False, schema='app')
        op.drop_constraint(op.f(f'fk_{table}_catalog_revision_id_public_catalog_revisions'), table, schema='app', type_='foreignkey')
        op.drop_column(table, 'catalog_revision_id', schema='app')
    op.drop_table('project_catalog_selections', schema='app')
    op.drop_table('public_catalog_revisions', schema='app')
    op.alter_column('projects', 'workspace_id', nullable=False, schema='app')
