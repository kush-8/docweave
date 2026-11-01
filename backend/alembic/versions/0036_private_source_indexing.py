"""Durable private source index intents, fenced leases and narrow paid-response recovery."""
from alembic import op
import sqlalchemy as sa
revision='0036_private_source_indexing'
down_revision='0035_source_media'
branch_labels=None
depends_on=None

FUNCTIONS={
'app.private_index_enqueue(uuid,uuid,uuid)':r"""
CREATE FUNCTION app.private_index_enqueue(p_actor uuid,p_document uuid,p_generation uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE d app.documents%ROWTYPE; p app.projects%ROWTYPE; result uuid;
BEGIN
 SELECT docs.* INTO d FROM app.documents docs JOIN app.collections c ON c.id=docs.collection_id
 JOIN app.projects project ON project.id=c.project_id WHERE docs.id=p_document AND docs.deleted_at IS NULL AND project.owner_user_id=p_actor AND project.workspace_id IS NULL;
 IF d.id IS NULL OR d.active_version_id IS NULL OR NOT app.personal_assessment_eligible(d.active_version_id) THEN RETURN NULL; END IF;
 SELECT project.* INTO p FROM app.projects project JOIN app.collections c ON c.project_id=project.id WHERE c.id=d.collection_id;
 PERFORM set_config('docweave.actor_id',p_actor::text,true),set_config('docweave.personal_project_id',p.id::text,true);
 IF NOT app.index_source_current(d.id) OR NOT app.personal_index_policy(d.collection_id,p_generation) THEN RETURN NULL; END IF;
 IF EXISTS(SELECT 1 FROM app.document_indexes WHERE document_id=d.id AND generation_id=p_generation AND document_version_id=d.active_version_id) THEN RETURN NULL; END IF;
 INSERT INTO app.private_index_jobs(document_id,document_version_id,generation_id,actor_id)
 VALUES(d.id,d.active_version_id,p_generation,p_actor)
 ON CONFLICT(document_id,document_version_id,generation_id) DO NOTHING;
 SELECT id INTO result FROM app.private_index_jobs WHERE document_id=d.id AND document_version_id=d.active_version_id AND generation_id=p_generation;
 RETURN result;
END $$""",
'app.private_index_claim(uuid)':r"""
CREATE FUNCTION app.private_index_claim(p_job uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.private_index_jobs%ROWTYPE; project uuid;
BEGIN
 UPDATE app.private_index_jobs SET status='running',lease_token=gen_random_uuid(),lease_expires_at=now()+interval '2 minutes',key_hash=NULL
 WHERE id=p_job AND (status IN ('queued','capacity') OR status='running' AND lease_expires_at<now()) RETURNING * INTO j;
 IF j.id IS NULL THEN RETURN NULL; END IF;
 SELECT c.project_id INTO project FROM app.documents d JOIN app.collections c ON c.id=d.collection_id WHERE d.id=j.document_id;
 RETURN jsonb_build_object('id',j.id,'lease_token',j.lease_token,'actor_id',j.actor_id,'project_id',project,'document_id',j.document_id,'generation_id',j.generation_id);
END $$""",
'app.private_index_context(uuid,uuid,uuid,text)':r"""
CREATE FUNCTION app.private_index_context(p_job uuid,p_token uuid,p_profile uuid,p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.private_index_jobs%ROWTYPE; p app.projects%ROWTYPE; d app.documents%ROWTYPE; session app.auth_sessions%ROWTYPE; subject text;
BEGIN
 SELECT * INTO j FROM app.private_index_jobs WHERE id=p_job AND status='running' AND lease_token=p_token AND lease_expires_at>now() FOR UPDATE;
 IF j.id IS NULL THEN RETURN NULL; END IF;
 SELECT docs.* INTO d FROM app.documents docs WHERE docs.id=j.document_id AND docs.deleted_at IS NULL AND docs.active_version_id=j.document_version_id;
 SELECT project.* INTO p FROM app.projects project JOIN app.collections c ON c.project_id=project.id WHERE c.id=d.collection_id AND project.owner_user_id=j.actor_id AND project.workspace_id IS NULL FOR SHARE OF project;
 SELECT * INTO session FROM app.auth_sessions WHERE user_id=j.actor_id AND expires_at>now() ORDER BY expires_at DESC LIMIT 1;
 SELECT u.subject INTO subject FROM app.users u WHERE u.id=j.actor_id AND u.issuer='https://github.com' AND u.subject ~ '^[0-9]+$';
 IF p.id IS NULL OR session.token_hash IS NULL OR subject IS NULL OR NOT app.personal_embedding_matches(j.generation_id,p_profile)
 OR NOT app.personal_assessment_eligible(j.document_version_id) THEN RETURN NULL; END IF;
 PERFORM set_config('docweave.actor_id',j.actor_id::text,true),set_config('docweave.personal_project_id',p.id::text,true);
 IF NOT app.index_source_current(d.id) OR NOT app.personal_index_policy(d.collection_id,j.generation_id) THEN RETURN NULL; END IF;
 PERFORM app.index_input(j.document_id,j.generation_id);
 PERFORM app.lock_budget();
 IF (SELECT coalesce(sum(charged_usd),0) FROM app.cost_reservations WHERE month=app.budget_month(statement_timestamp()))>20 THEN RETURN NULL; END IF;
 IF p_key IS NOT NULL AND p_key !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
 UPDATE app.private_index_jobs SET lease_expires_at=now()+interval '2 minutes',key_hash=p_key,profile_id=p_profile WHERE id=j.id;
 RETURN jsonb_build_object('encrypted_token',session.encrypted_token,'github_subject',subject,'repository_id',p.repository_id);
END $$""",
'app.private_index_finish(uuid,uuid,text)':r"""
CREATE FUNCTION app.private_index_finish(p_job uuid,p_token uuid,p_status text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF p_status NOT IN ('completed','capacity','completion_unknown','failed') THEN RAISE EXCEPTION 'Invalid status' USING ERRCODE='22023'; END IF;
 UPDATE app.private_index_jobs SET status=p_status,lease_expires_at=NULL,key_hash=NULL WHERE id=p_job AND lease_token=p_token AND status='running' AND lease_expires_at>now();
 RETURN FOUND;
END $$""",
'app.private_index_reconcile(uuid)':r"""
CREATE FUNCTION app.private_index_reconcile(p_generation uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE d record; j record; n integer:=0; queued bigint;
BEGIN
 FOR d IN SELECT docs.id,p.owner_user_id FROM app.documents docs JOIN app.collections c ON c.id=docs.collection_id JOIN app.projects p ON p.id=c.project_id
 WHERE p.workspace_id IS NULL AND docs.deleted_at IS NULL AND docs.active_version_id IS NOT NULL AND app.personal_assessment_eligible(docs.active_version_id)
 AND (docs.source_id IS NULL OR EXISTS(SELECT 1 FROM app.sources source JOIN app.documentation_selections ds ON ds.id=source.source_selection_id
  WHERE source.id=docs.source_id AND source.deleted_at IS NULL AND ds.active AND ds.project_id=p.id
  AND EXISTS(SELECT 1 FROM jsonb_array_elements(p.stack) dep WHERE dep=ds.approved_stack)))
 AND EXISTS(SELECT 1 FROM app.index_generations g WHERE g.id=p_generation AND g.enabled AND NOT EXISTS(
  SELECT 1 FROM jsonb_array_elements_text(g.processor_ids) wanted(id) LEFT JOIN app.processors processor ON processor.id=wanted.id
  WHERE processor.id IS NULL OR NOT processor.enabled
  OR NOT EXISTS(SELECT 1 FROM app.project_processor_approvals a WHERE a.project_id=p.id AND a.processor_id=wanted.id)
  OR NOT EXISTS(SELECT 1 FROM app.collection_processor_approvals a WHERE a.collection_id=c.id AND a.processor_id=wanted.id)))
 AND NOT EXISTS(SELECT 1 FROM app.document_indexes i WHERE i.document_id=docs.id AND i.document_version_id=docs.active_version_id AND i.generation_id=p_generation)
 AND NOT EXISTS(SELECT 1 FROM app.private_index_jobs jobs WHERE jobs.document_id=docs.id AND jobs.document_version_id=docs.active_version_id AND jobs.generation_id=p_generation)
 ORDER BY docs.created_at,docs.id LIMIT 100 LOOP
  PERFORM app.private_index_enqueue(d.owner_user_id,d.id,p_generation);
 END LOOP;
 FOR j IN SELECT jobs.* FROM app.private_index_jobs jobs WHERE generation_id=p_generation
 AND (status IN ('queued','capacity') OR status='running' AND lease_expires_at<now())
 AND NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.private_index' AND q.args->>'job_id'=jobs.id::text AND q.status IN ('todo','doing'))
 ORDER BY coalesce((SELECT max(q.id) FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.private_index' AND q.args->>'job_id'=jobs.id::text),0),jobs.created_at,jobs.id LIMIT 100 FOR UPDATE SKIP LOCKED LOOP
  SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.private_index',0,'private-index:'||j.id::text,NULL,jsonb_build_object('job_id',j.id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
  n:=n+1;
 END LOOP;
 RETURN n;
END $$""",
}

CHECKPOINT_OLD="IF NOT FOUND THEN RAISE EXCEPTION 'Recovery authority changed' USING ERRCODE='42501'; END IF;"
CHECKPOINT_NEW="""IF NOT FOUND AND NOT EXISTS(
   SELECT 1 FROM app.personal_provider_calls calls JOIN app.cost_reservations r ON r.id=calls.reservation_id
   JOIN app.private_index_jobs j ON j.actor_id=r.actor_id AND j.profile_id=r.profile_id AND j.key_hash=calls.key_hash
   JOIN app.documents d ON d.id=j.document_id AND d.active_version_id=j.document_version_id AND d.deleted_at IS NULL
   JOIN app.collections c ON c.id=d.collection_id AND c.project_id=r.project_id
   JOIN app.projects p ON p.id=c.project_id AND p.owner_user_id=j.actor_id
   WHERE r.id=p_id AND j.status='running' AND j.lease_expires_at>now()
   AND app.private_index_context(j.id,j.lease_token,j.profile_id,j.key_hash) IS NOT NULL
  ) THEN RAISE EXCEPTION 'Recovery authority changed' USING ERRCODE='42501'; END IF;"""

def replace(before,after):
    definition=op.get_bind().scalar(sa.text("SELECT pg_get_functiondef('app.personal_provider_checkpoint(uuid,jsonb)'::regprocedure)"))
    if before not in definition:
        raise ValueError('Unexpected checkpoint authority')
    op.execute(definition.replace(before,after))

def upgrade():
    op.create_table('private_index_jobs',sa.Column('id',sa.UUID(),primary_key=True,server_default=sa.text('gen_random_uuid()')),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.text('now()'),nullable=False),
        sa.Column('document_id',sa.UUID(),sa.ForeignKey('app.documents.id',ondelete='RESTRICT'),nullable=False),sa.Column('document_version_id',sa.UUID(),sa.ForeignKey('app.document_versions.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('generation_id',sa.UUID(),sa.ForeignKey('app.index_generations.id',ondelete='RESTRICT'),nullable=False),sa.Column('actor_id',sa.UUID(),sa.ForeignKey('app.users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('status',sa.Text(),nullable=False,server_default='queued'),sa.Column('lease_token',sa.UUID()),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),sa.Column('key_hash',sa.Text()),
        sa.Column('profile_id',sa.UUID(),sa.ForeignKey('app.provider_profiles.id',ondelete='RESTRICT')),sa.UniqueConstraint('document_id','document_version_id','generation_id',name='uq_private_index_intent'),schema='app')
    op.execute('ALTER TABLE app.private_index_jobs ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON app.private_index_jobs FROM PUBLIC,docweave_runtime,docweave_worker')
    for signature,sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
        op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')
    replace(CHECKPOINT_OLD,CHECKPOINT_NEW)

def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.private_index_jobs) THEN RAISE EXCEPTION 'Preserve private indexing intents before downgrade'; END IF; END $$")
    replace(CHECKPOINT_NEW,CHECKPOINT_OLD)
    for signature in reversed(FUNCTIONS):
        op.execute(f'DROP FUNCTION {signature}')
    op.drop_table('private_index_jobs',schema='app')
