"""Personal shared/private retrieval eligibility and exact-version guard assessments."""
from alembic import op
import sqlalchemy as sa
revision='0017_personal_retrieval'
down_revision='0016_personal_conversations'
branch_labels=None
depends_on=None

def upgrade():
 op.create_table('document_assessments',sa.Column('document_version_id',sa.UUID(),sa.ForeignKey('app.document_versions.id',ondelete='RESTRICT'),primary_key=True),sa.Column('content_hash',sa.Text(),nullable=False),sa.Column('parser_config_hash',sa.Text(),nullable=False),sa.Column('rule_revision',sa.Text(),nullable=False),sa.Column('credential_blocked',sa.Boolean(),nullable=False),sa.Column('injection_flagged',sa.Boolean(),nullable=False),sa.Column('complete',sa.Boolean(),nullable=False),sa.Column('reviewed_by',sa.UUID(),sa.ForeignKey('app.users.id',ondelete='RESTRICT')),schema='app')
 op.execute('ALTER TABLE app.document_assessments ENABLE ROW LEVEL SECURITY')
 op.execute('REVOKE ALL ON app.document_assessments FROM PUBLIC,docweave_runtime,docweave_worker')
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC')
  if not signature.startswith('app.personal_assessment_eligible'):
   op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime,docweave_worker')
 op.execute("CREATE POLICY personal_owner_read ON app.projects FOR SELECT TO docweave_runtime USING (app.personal_project_owned(id))")
 op.execute("CREATE POLICY personal_scope_read ON app.collections FOR SELECT TO docweave_runtime USING (app.personal_collection_allowed(id))")
 op.execute("CREATE POLICY personal_scope_read ON app.chunks FOR SELECT TO docweave_runtime USING (app.personal_chunk_allowed(document_version_id,collection_id,generation_id))")

FUNCTIONS={
'app.personal_assessment_eligible(uuid)':r"""
CREATE FUNCTION app.personal_assessment_eligible(p_version uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.document_assessments a JOIN app.document_versions v ON v.id=a.document_version_id
 WHERE v.id=p_version AND a.content_hash=v.content_hash AND a.rule_revision='deterministic-v1' AND a.complete
 AND NOT a.credential_blocked AND (NOT a.injection_flagged OR a.reviewed_by IS NOT NULL))
$$""",
'app.personal_collection_allowed(uuid)':r"""
CREATE FUNCTION app.personal_collection_allowed(p_collection uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.collections c WHERE c.id=p_collection AND (
 (c.project_id=nullif(current_setting('docweave.personal_project_id',true),'')::uuid AND app.personal_project_owned(c.project_id))
 OR (c.catalog_revision_id IS NOT NULL AND EXISTS(
 SELECT 1 FROM app.project_catalog_selections s JOIN app.public_catalog_revisions r ON r.id=s.catalog_revision_id
 JOIN app.projects p ON p.id=s.project_id
 WHERE s.catalog_revision_id=c.catalog_revision_id AND s.project_id=nullif(current_setting('docweave.personal_project_id',true),'')::uuid
 AND app.personal_project_owned(s.project_id) AND r.enabled AND r.source_approved
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) d WHERE d->>'id'=s.dependency_id
 AND lower(d->>'technology')=lower(r.technology) AND (
 (r.coverage->>'granularity'='exact' AND d->>'docs_target'=r.coverage->>'version') OR
 (s.fallback_accepted AND ((r.coverage->>'granularity'='major' AND split_part(d->>'docs_target','.',1)=r.coverage->>'version')
 OR(r.coverage->>'granularity'='minor' AND split_part(d->>'docs_target','.',1)||'.'||split_part(d->>'docs_target','.',2)=r.coverage->>'version')))))))
 ))
$$""",
'app.personal_index_policy(uuid,uuid)':r"""
CREATE FUNCTION app.personal_index_policy(p_collection uuid,p_generation uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.collections c JOIN app.index_generations g ON g.id=p_generation
 WHERE c.id=p_collection AND app.personal_collection_allowed(c.id) AND g.enabled AND (
 c.catalog_revision_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(g.processor_ids) wanted(id)
 LEFT JOIN app.processors processor ON processor.id=wanted.id
 WHERE processor.id IS NULL OR NOT processor.enabled OR NOT EXISTS(SELECT 1 FROM app.project_processor_approvals a WHERE a.project_id=c.project_id AND a.processor_id=processor.id)
 OR NOT EXISTS(SELECT 1 FROM app.collection_processor_approvals a WHERE a.collection_id=c.id AND a.processor_id=processor.id))))
$$""",
'app.personal_chunk_allowed(uuid,uuid,uuid)':r"""
CREATE FUNCTION app.personal_chunk_allowed(p_version uuid,p_collection uuid,p_generation uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.document_indexes i JOIN app.document_versions v ON v.id=i.document_version_id
 JOIN app.documents d ON d.id=i.document_id JOIN app.collections c ON c.id=d.collection_id
 LEFT JOIN app.sources s ON s.id=d.source_id LEFT JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
 WHERE i.document_version_id=p_version AND d.collection_id=p_collection AND i.generation_id=p_generation
 AND p_generation=nullif(current_setting('docweave.generation_id',true),'')::uuid AND d.deleted_at IS NULL
 AND app.personal_index_policy(p_collection,p_generation) AND app.personal_assessment_eligible(p_version)
 AND (d.source_id IS NULL OR (s.deleted_at IS NULL AND ds.active AND (
 (c.catalog_revision_id IS NOT NULL AND ds.catalog_revision_id=c.catalog_revision_id)
 OR(c.project_id IS NOT NULL AND ds.project_id=c.project_id AND EXISTS(SELECT 1 FROM app.projects p,jsonb_array_elements(p.stack) dep WHERE p.id=c.project_id AND dep=ds.approved_stack)))))
 )
$$""",
}

def downgrade():
 op.execute('DROP POLICY personal_scope_read ON app.chunks')
 op.execute('DROP POLICY personal_scope_read ON app.collections')
 op.execute('DROP POLICY personal_owner_read ON app.projects')
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
 op.drop_table('document_assessments',schema='app')
