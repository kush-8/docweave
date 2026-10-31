"""Durable personal chat intent and restricted worker claims."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0016_personal_conversations'
down_revision='0015_personal_projects'
branch_labels=None
depends_on=None

def record():
 return [sa.Column('id',sa.UUID(),primary_key=True,server_default=sa.text('gen_random_uuid()')),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now())]

def upgrade():
 op.create_table('conversations',*record(),sa.Column('project_id',sa.UUID(),sa.ForeignKey('app.projects.id',ondelete='RESTRICT'),nullable=False),sa.Column('answer_profile_id',sa.UUID(),sa.ForeignKey('app.provider_profiles.id',ondelete='RESTRICT')),sa.Column('status',sa.Text(),nullable=False,server_default='initializing'),sa.Column('deleted_at',sa.DateTime(timezone=True)),schema='app')
 op.create_table('turns',*record(),sa.Column('conversation_id',sa.UUID(),sa.ForeignKey('app.conversations.id',ondelete='RESTRICT'),nullable=False),sa.Column('sequence',sa.Integer(),nullable=False),sa.Column('idempotency_key',sa.UUID(),nullable=False),sa.Column('message',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False,server_default='queued'),sa.Column('answer',sa.Text()),sa.Column('context_revision',sa.Integer()),sa.Column('required_dependencies',JSONB(),nullable=False,server_default='[]'),sa.Column('citations',JSONB(),nullable=False,server_default='[]'),sa.Column('progress',sa.Text()),sa.UniqueConstraint('conversation_id','idempotency_key',name='uq_turns_intent'),sa.UniqueConstraint('conversation_id','sequence',name='uq_turns_sequence'),schema='app')
 op.create_index('uq_turns_active','turns',['conversation_id'],unique=True,postgresql_where=sa.text("status IN ('queued','running','waiting_for_sources')"),schema='app')
 op.create_table('personal_jobs',*record(),sa.Column('conversation_id',sa.UUID(),sa.ForeignKey('app.conversations.id',ondelete='RESTRICT'),nullable=False),sa.Column('turn_id',sa.UUID(),sa.ForeignKey('app.turns.id',ondelete='RESTRICT')),sa.Column('actor_id',sa.UUID(),sa.ForeignKey('app.users.id',ondelete='RESTRICT'),nullable=False),sa.Column('kind',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False,server_default='queued'),sa.Column('lease_token',sa.UUID()),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),schema='app')
 for table in ('conversations','turns','personal_jobs'):
  op.execute(f'ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY')
  op.execute(f'REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime,docweave_worker')
 for signature,sql in FUNCTIONS.items():
  op.execute(sql)
  op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
  role='docweave_worker' if signature.startswith(('app.personal_claim_job','app.personal_finish_job','app.personal_pending_jobs')) else 'docweave_runtime'
  if not signature.startswith('app.personal_enqueue('):
   op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO {role}')

FUNCTIONS={
'app.personal_enqueue(uuid,uuid,text)':r"""
CREATE FUNCTION app.personal_enqueue(p_conversation uuid,p_turn uuid,p_kind text) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE job uuid; project uuid; queued bigint;
BEGIN
 SELECT project_id INTO project FROM app.conversations WHERE id=p_conversation;
 INSERT INTO app.personal_jobs(conversation_id,turn_id,actor_id,kind) VALUES(p_conversation,p_turn,nullif(current_setting('docweave.actor_id',true),'')::uuid,p_kind) RETURNING id INTO job;
 SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.personal',0,'personal:'||project::text,NULL,jsonb_build_object('job_id',job),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
 RETURN job;
END $$""",
'app.personal_conversation(uuid)':r"""
CREATE FUNCTION app.personal_conversation(p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',c.id,'project_id',c.project_id,'status',c.status,'created_at',c.created_at,'answer_profile_id',c.answer_profile_id)
 FROM app.conversations c WHERE c.id=p_id AND c.deleted_at IS NULL AND app.personal_project_owned(c.project_id)
$$""",
'app.personal_create_conversation(uuid,uuid)':r"""
CREATE FUNCTION app.personal_create_conversation(p_project uuid,p_profile uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE conversation uuid;
BEGIN
 PERFORM 1 FROM app.projects WHERE id=p_project AND app.personal_project_owned(id) AND repository_id IS NOT NULL FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Repository setup required' USING ERRCODE='P0002'; END IF;
 IF p_profile IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.provider_profiles WHERE id=p_profile AND role='generation' AND app.profile_disabled_reason(id) IS NULL) THEN
 RAISE EXCEPTION 'Profile unavailable' USING ERRCODE='DW010'; END IF;
 INSERT INTO app.conversations(project_id,answer_profile_id) VALUES(p_project,p_profile) RETURNING id INTO conversation;
 PERFORM app.personal_enqueue(conversation,NULL,'sync');
 RETURN app.personal_conversation(conversation);
END $$""",
'app.personal_turn(uuid)':r"""
CREATE FUNCTION app.personal_turn(p_id uuid) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT jsonb_build_object('id',t.id,'conversation_id',t.conversation_id,'sequence',t.sequence,'message',t.message,'status',t.status,'answer',t.answer,'citations',t.citations,'context_revision',t.context_revision,'progress',t.progress,'created_at',t.created_at)
 FROM app.turns t JOIN app.conversations c ON c.id=t.conversation_id WHERE t.id=p_id AND c.deleted_at IS NULL AND app.personal_project_owned(c.project_id)
$$""",
'app.personal_append_turn(uuid,uuid,text)':r"""
CREATE FUNCTION app.personal_append_turn(p_conversation uuid,p_key uuid,p_message text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE conversation app.conversations%ROWTYPE; old app.turns%ROWTYPE; turn_id uuid;
BEGIN
 SELECT * INTO conversation FROM app.conversations WHERE id=p_conversation AND deleted_at IS NULL AND app.personal_project_owned(project_id) FOR UPDATE;
 IF conversation.id IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 SELECT * INTO old FROM app.turns WHERE conversation_id=p_conversation AND idempotency_key=p_key;
 IF old.id IS NOT NULL THEN
  IF old.message<>p_message THEN RAISE EXCEPTION 'Intent conflict' USING ERRCODE='40001'; END IF;
  RETURN app.personal_turn(old.id);
 END IF;
 IF conversation.status<>'ready' OR EXISTS(SELECT 1 FROM app.turns WHERE conversation_id=p_conversation AND status IN ('queued','running','waiting_for_sources')) THEN
 RAISE EXCEPTION 'Conversation busy' USING ERRCODE='40001'; END IF;
 IF p_key IS NULL OR p_message !~ '[^[:space:]]' OR length(p_message)>16000 THEN RAISE EXCEPTION 'Invalid turn' USING ERRCODE='22023'; END IF;
 INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message) SELECT p_conversation,coalesce(max(sequence),0)+1,p_key,p_message FROM app.turns WHERE conversation_id=p_conversation RETURNING id INTO turn_id;
 PERFORM app.personal_enqueue(p_conversation,turn_id,'answer');
 RETURN app.personal_turn(turn_id);
END $$""",
'app.personal_list_conversations(uuid)':r"""
CREATE FUNCTION app.personal_list_conversations(p_project uuid) RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT app.personal_conversation(id) FROM app.conversations WHERE project_id=p_project AND deleted_at IS NULL AND app.personal_project_owned(project_id) ORDER BY created_at,id
$$""",
'app.personal_list_turns(uuid)':r"""
CREATE FUNCTION app.personal_list_turns(p_conversation uuid) RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT app.personal_turn(t.id) FROM app.turns t JOIN app.conversations c ON c.id=t.conversation_id WHERE c.id=p_conversation AND c.deleted_at IS NULL AND app.personal_project_owned(c.project_id) ORDER BY t.sequence
$$""",
'app.personal_delete_conversation(uuid)':r"""
CREATE FUNCTION app.personal_delete_conversation(p_id uuid) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 UPDATE app.conversations SET deleted_at=now(),status='deleted' WHERE id=p_id AND app.personal_project_owned(project_id);
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE app.turns SET status='cancelled' WHERE conversation_id=p_id AND status IN ('queued','running','waiting_for_sources');
 UPDATE app.personal_jobs SET status='cancelled',lease_token=NULL WHERE conversation_id=p_id AND status IN ('queued','running','waiting');
 RETURN true;
END $$""",
'app.personal_claim_job(uuid)':r"""
CREATE FUNCTION app.personal_claim_job(p_id uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE job app.personal_jobs%ROWTYPE; conversation app.conversations%ROWTYPE; project app.projects%ROWTYPE; session app.auth_sessions%ROWTYPE; identity app.users%ROWTYPE;
BEGIN
 SELECT * INTO job FROM app.personal_jobs WHERE id=p_id FOR UPDATE;
 IF job.id IS NULL OR job.status NOT IN ('queued','waiting') AND NOT(job.status='running' AND job.lease_expires_at<now()) THEN RETURN NULL; END IF;
 SELECT * INTO conversation FROM app.conversations WHERE id=job.conversation_id AND deleted_at IS NULL;
 SELECT * INTO project FROM app.projects WHERE id=conversation.project_id AND owner_user_id=job.actor_id;
 IF project.id IS NULL THEN UPDATE app.personal_jobs SET status='cancelled' WHERE id=p_id; RETURN NULL; END IF;
 SELECT * INTO session FROM app.auth_sessions WHERE user_id=job.actor_id AND expires_at>now() ORDER BY expires_at DESC LIMIT 1;
 SELECT * INTO identity FROM app.users WHERE id=job.actor_id;
 IF session.token_hash IS NULL OR identity.issuer<>'https://github.com' THEN
 UPDATE app.personal_jobs SET status='failed' WHERE id=p_id;
 UPDATE app.conversations SET status='blocked' WHERE id=conversation.id AND job.kind='sync';
 UPDATE app.turns SET status='blocked_policy',progress='Sign in with GitHub again.' WHERE id=job.turn_id; RETURN NULL; END IF;
 UPDATE app.personal_jobs SET status='running',lease_token=gen_random_uuid(),lease_expires_at=now()+interval '2 minutes' WHERE id=p_id RETURNING * INTO job;
 PERFORM set_config('docweave.actor_id',job.actor_id::text,true);
 IF job.kind='answer' THEN UPDATE app.turns SET status='running',context_revision=project.context_revision,progress='Checking documentation' WHERE id=job.turn_id; END IF;
 RETURN jsonb_build_object('id',job.id,'lease_token',job.lease_token,'actor_id',job.actor_id,'kind',job.kind,'project',app.personal_project(project.id),'conversation',app.personal_conversation(conversation.id),'turn',app.personal_turn(job.turn_id),'encrypted_token',session.encrypted_token,'github_subject',identity.subject);
END $$""",
'app.personal_finish_job(uuid,uuid,jsonb)':r"""
CREATE FUNCTION app.personal_finish_job(p_id uuid,p_token uuid,p_result jsonb) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE job app.personal_jobs%ROWTYPE; conversation app.conversations%ROWTYPE; project app.projects%ROWTYPE;
BEGIN
 SELECT * INTO job FROM app.personal_jobs WHERE id=p_id AND status='running' AND lease_token=p_token AND lease_expires_at>now() FOR UPDATE;
 IF job.id IS NULL THEN RETURN false; END IF;
 SELECT * INTO conversation FROM app.conversations WHERE id=job.conversation_id AND deleted_at IS NULL;
 SELECT * INTO project FROM app.projects WHERE id=conversation.project_id AND owner_user_id=job.actor_id FOR UPDATE;
 IF project.id IS NULL THEN RETURN false; END IF;
 IF job.kind='sync' THEN
  IF p_result->>'status'='ready' AND (p_result->>'expected_revision')::integer=project.context_revision THEN
   UPDATE app.projects SET stack=p_result->'stack',stack_fingerprint=p_result->>'stack_fingerprint',last_commit_sha=p_result->>'last_commit_sha',context_revision=(p_result->>'context_revision')::integer,sync_status='ready' WHERE id=project.id;
   UPDATE app.conversations SET status='ready' WHERE id=conversation.id;
  ELSE
   UPDATE app.projects SET sync_status='failed' WHERE id=project.id;
   UPDATE app.conversations SET status='blocked' WHERE id=conversation.id;
  END IF;
 ELSE
  IF p_result->>'status' NOT IN ('completed','failed','blocked_policy','waiting_for_sources','completion_unknown') THEN RAISE EXCEPTION 'Invalid state' USING ERRCODE='22023'; END IF;
  UPDATE app.turns SET status=p_result->>'status',answer=p_result->>'answer',citations=coalesce(p_result->'citations','[]'),required_dependencies=coalesce(p_result->'required_dependencies','[]'),progress=p_result->>'progress' WHERE id=job.turn_id;
 END IF;
 UPDATE app.personal_jobs SET status=CASE WHEN p_result->>'status'='waiting_for_sources' THEN 'waiting' ELSE 'completed' END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_id;
 RETURN true;
END $$""",
'app.personal_pending_jobs()':r"""
CREATE FUNCTION app.personal_pending_jobs() RETURNS TABLE(id uuid,project_id uuid) LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT j.id,c.project_id FROM app.personal_jobs j JOIN app.conversations c ON c.id=j.conversation_id WHERE c.deleted_at IS NULL AND (j.status IN ('queued','waiting') OR j.status='running' AND j.lease_expires_at<now()) ORDER BY j.created_at LIMIT 100
$$""",
}

def downgrade():
 for signature in reversed(FUNCTIONS):
  op.execute(f'DROP FUNCTION {signature}')
 for table in ('personal_jobs','turns','conversations'):
  op.drop_table(table,schema='app')
