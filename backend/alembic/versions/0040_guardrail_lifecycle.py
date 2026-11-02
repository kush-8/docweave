"""Current rule epochs, durable local rescans and version-bound review audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0040_guardrail_lifecycle'
down_revision='0039_conversation_summaries'
branch_labels=None
depends_on=None
INITIAL_REVISION='deterministic-9335fe8432887ba7de73ee29c411747c1b9a7f1d59d57edc3eb285d0a1937ffe'

FUNCTIONS={
'app.guardrail_fence(text,bigint)':r"""
CREATE FUNCTION app.guardrail_fence(p_revision text,p_epoch bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 IF policy.rule_revision IS DISTINCT FROM p_revision OR (p_epoch IS NOT NULL AND policy.epoch<>p_epoch) THEN
  RAISE EXCEPTION 'Guardrail policy changed' USING ERRCODE='42501';
 END IF;
 RETURN jsonb_build_object('rule_revision',policy.rule_revision,'epoch',policy.epoch);
END $$""",
'app.activate_guardrail_policy(text,bigint)':r"""
CREATE FUNCTION app.activate_guardrail_policy(p_revision text,p_expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR UPDATE;
 IF policy.epoch IS DISTINCT FROM p_expected OR p_revision IS NULL OR p_revision !~ '^[a-zA-Z0-9_-]{1,100}$' THEN
  RAISE EXCEPTION 'Stale or invalid rule activation' USING ERRCODE='22023';
 END IF;
 UPDATE app.guardrail_policy SET rule_revision=p_revision,epoch=epoch+1 WHERE id=1 RETURNING * INTO policy;
 INSERT INTO app.guardrail_events(epoch,rule_revision,kind) VALUES(policy.epoch,policy.rule_revision,'activated');
 UPDATE app.conversations SET summary=NULL WHERE summary IS NOT NULL;
 RETURN jsonb_build_object('rule_revision',policy.rule_revision,'epoch',policy.epoch);
END $$""",
'app.personal_assessment_eligible(uuid)':r"""
CREATE OR REPLACE FUNCTION app.personal_assessment_eligible(p_version uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.document_assessments a JOIN app.document_versions v ON v.id=a.document_version_id
 JOIN app.documents d ON d.id=v.document_id JOIN app.collections c ON c.id=d.collection_id
 JOIN app.guardrail_policy policy ON policy.id=1
 WHERE v.id=p_version AND d.deleted_at IS NULL AND a.content_hash=v.content_hash
 AND a.parser_config_hash=encode(sha256(convert_to('{"configuration":'||to_json(v.configuration)::text||'}','UTF8')),'hex')
 AND a.rule_revision=policy.rule_revision AND a.policy_epoch=policy.epoch AND a.complete AND NOT a.credential_blocked
 AND (NOT a.injection_flagged OR
 (c.project_id IS NOT NULL AND EXISTS(SELECT 1 FROM app.projects p WHERE p.id=c.project_id AND p.owner_user_id=a.reviewed_by)) OR
 (c.catalog_revision_id IS NOT NULL AND a.reviewed_by='60000000-0000-4000-8000-000000000001')))
$$""",
'app.guardrail_document_state(uuid)':r"""
CREATE FUNCTION app.guardrail_document_state(p_version uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT CASE WHEN a.policy_epoch IS DISTINCT FROM policy.epoch OR a.rule_revision IS DISTINCT FROM policy.rule_revision
 THEN CASE WHEN r.status IN ('failed','cancelled') THEN 'failed' ELSE 'processing' END
 WHEN NOT app.personal_assessment_eligible(v.id) THEN 'pending_review' ELSE NULL END
 FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id JOIN app.guardrail_policy policy ON policy.id=1
 LEFT JOIN app.document_assessments a ON a.document_version_id=v.id
 LEFT JOIN app.guardrail_rescans r ON r.document_version_id=v.id AND r.epoch=policy.epoch
 WHERE v.id=p_version AND d.deleted_at IS NULL
$$""",
'app.personal_version_assessment_view(uuid,uuid)':r"""
CREATE FUNCTION app.personal_version_assessment_view(p_document uuid,p_version uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT to_jsonb(a)||jsonb_build_object('document_id',d.id,'status',d.status,'eligible',app.personal_assessment_eligible(a.document_version_id),
 'current_rule_revision',policy.rule_revision,'current_policy_epoch',policy.epoch,'rescan_status',app.guardrail_document_state(a.document_version_id))
 FROM app.documents d JOIN app.collections c ON c.id=d.collection_id JOIN app.document_versions v ON v.document_id=d.id AND v.id=coalesce(p_version,d.active_version_id)
 JOIN app.document_assessments a ON a.document_version_id=v.id
 JOIN app.guardrail_policy policy ON policy.id=1 WHERE d.id=p_document AND d.deleted_at IS NULL AND app.personal_project_owned(c.project_id)
$$""",
'app.personal_assessment_view(uuid)':r"""
CREATE OR REPLACE FUNCTION app.personal_assessment_view(p_document uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT app.personal_version_assessment_view(p_document,NULL)
$$""",
'app.guardrail_restore_document(uuid)':r"""
CREATE FUNCTION app.guardrail_restore_document(p_version uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 UPDATE app.documents d SET status=CASE WHEN NOT app.personal_assessment_eligible(p_version) THEN 'quarantined'
 WHEN EXISTS(SELECT 1 FROM app.document_indexes i JOIN app.index_generations g ON g.id=i.generation_id WHERE i.document_id=d.id AND i.document_version_id=p_version AND g.enabled) THEN 'ready'
 WHEN EXISTS(SELECT 1 FROM app.document_indexes i WHERE i.document_id=d.id AND i.document_version_id<>p_version) THEN 'stale'
 WHEN d.status IN ('quarantined','ready') THEN 'waiting_capacity' ELSE d.status END
 WHERE d.active_version_id=p_version AND d.deleted_at IS NULL;
 IF app.personal_assessment_eligible(p_version) THEN
  UPDATE app.catalog_jobs j SET status='capacity',stage='Waiting for current indexing authority'
  FROM app.documents d,app.collections c,app.public_catalog_revisions r
  WHERE d.active_version_id=p_version AND c.id=d.collection_id AND r.id=c.catalog_revision_id AND r.enabled AND r.source_approved
  AND j.document_id=d.id AND j.status='pending_review';
 END IF;
END $$""",
'app.guardrail_store_assessment(uuid,jsonb)':r"""
CREATE FUNCTION app.guardrail_store_assessment(p_version uuid,p_assessment jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE; v app.document_versions%ROWTYPE;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 SELECT versions.* INTO v FROM app.document_versions versions JOIN app.documents d ON d.id=versions.document_id
 WHERE versions.id=p_version AND d.deleted_at IS NULL FOR UPDATE OF d;
 IF v.id IS NULL OR p_assessment->>'document_version' IS DISTINCT FROM v.id::text
 OR p_assessment->>'content_hash' IS DISTINCT FROM v.content_hash
 OR p_assessment->>'rule_revision' IS DISTINCT FROM policy.rule_revision
 OR p_assessment->>'parser_config_hash' IS DISTINCT FROM encode(sha256(convert_to('{"configuration":'||to_json(v.configuration)::text||'}','UTF8')),'hex')
 OR jsonb_typeof(p_assessment->'findings') IS DISTINCT FROM 'array'
 OR jsonb_array_length(p_assessment->'findings')>50
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_assessment->'findings') finding WHERE jsonb_typeof(finding)<>'string' OR finding#>>'{}' !~ '^[a-z0-9-]{1,100}$')
 OR jsonb_typeof(p_assessment->'complete') IS DISTINCT FROM 'boolean'
 OR jsonb_typeof(p_assessment->'credential_blocked') IS DISTINCT FROM 'boolean'
 OR jsonb_typeof(p_assessment->'injection_flagged') IS DISTINCT FROM 'boolean' THEN RETURN false; END IF;
 INSERT INTO app.document_assessments(document_version_id,content_hash,parser_config_hash,rule_revision,policy_epoch,findings,credential_blocked,injection_flagged,complete)
 VALUES(v.id,v.content_hash,p_assessment->>'parser_config_hash',policy.rule_revision,policy.epoch,p_assessment->'findings',
 (p_assessment->>'credential_blocked')::boolean,(p_assessment->>'injection_flagged')::boolean,(p_assessment->>'complete')::boolean)
 ON CONFLICT(document_version_id) DO UPDATE SET content_hash=excluded.content_hash,parser_config_hash=excluded.parser_config_hash,
 rule_revision=excluded.rule_revision,policy_epoch=excluded.policy_epoch,findings=excluded.findings,credential_blocked=excluded.credential_blocked,
 injection_flagged=excluded.injection_flagged,complete=excluded.complete,
 reviewed_by=CASE WHEN (app.document_assessments.content_hash,app.document_assessments.parser_config_hash,app.document_assessments.rule_revision,
 app.document_assessments.policy_epoch,app.document_assessments.credential_blocked,app.document_assessments.injection_flagged,app.document_assessments.complete)
 IS NOT DISTINCT FROM (excluded.content_hash,excluded.parser_config_hash,excluded.rule_revision,excluded.policy_epoch,excluded.credential_blocked,excluded.injection_flagged,excluded.complete)
 THEN app.document_assessments.reviewed_by ELSE NULL END;
 INSERT INTO app.guardrail_events(document_version_id,epoch,rule_revision,kind,findings) VALUES(v.id,policy.epoch,policy.rule_revision,'assessed',p_assessment->'findings');
 PERFORM app.guardrail_restore_document(v.id);
 RETURN true;
END $$""",
'app.assess_ingestion_version(uuid,jsonb)':r"""
CREATE OR REPLACE FUNCTION app.assess_ingestion_version(p_version uuid,p_assessment jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id
 WHERE v.id=p_version AND d.deleted_at IS NULL AND app.collection_can(d.collection_id,'write')) THEN RETURN false; END IF;
 RETURN app.guardrail_store_assessment(p_version,p_assessment);
END $$""",
'app.guardrail_reconcile(text)':r"""
CREATE FUNCTION app.guardrail_reconcile(p_revision text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE policy app.guardrail_policy%ROWTYPE; j record; n integer:=0; queued bigint;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 IF policy.rule_revision<>p_revision THEN RETURN 0; END IF;
 INSERT INTO app.guardrail_rescans(document_version_id,epoch,rule_revision)
 SELECT v.id,policy.epoch,policy.rule_revision FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id
 LEFT JOIN app.document_assessments a ON a.document_version_id=v.id
 WHERE d.deleted_at IS NULL AND (a.policy_epoch IS DISTINCT FROM policy.epoch OR a.rule_revision IS DISTINCT FROM policy.rule_revision)
 AND NOT EXISTS(SELECT 1 FROM app.guardrail_rescans r WHERE r.document_version_id=v.id AND r.epoch=policy.epoch)
 ORDER BY v.created_at,v.id LIMIT 100 ON CONFLICT(document_version_id,epoch) DO NOTHING;
 FOR j IN SELECT r.* FROM app.guardrail_rescans r WHERE r.epoch=policy.epoch
 AND (r.status='queued' OR r.status='running' AND r.lease_expires_at<now())
 AND NOT EXISTS(SELECT 1 FROM queue.procrastinate_jobs q WHERE q.task_name='docweave.guardrail_rescan' AND q.args->>'job_id'=r.id::text AND q.status IN ('todo','doing'))
 ORDER BY r.created_at,r.id LIMIT 100 FOR UPDATE SKIP LOCKED LOOP
  SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('personal','docweave.guardrail_rescan',0,'guardrail:'||j.id::text,NULL,jsonb_build_object('job_id',j.id),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queued;
  n:=n+1;
 END LOOP;
 RETURN n;
END $$""",
'app.guardrail_claim(uuid,text)':r"""
CREATE FUNCTION app.guardrail_claim(p_job uuid,p_revision text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE; j app.guardrail_rescans%ROWTYPE; v app.document_versions%ROWTYPE;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 IF policy.rule_revision<>p_revision THEN RETURN NULL; END IF;
 UPDATE app.guardrail_rescans SET status='running',lease_token=gen_random_uuid(),lease_expires_at=now()+interval '2 minutes'
 WHERE id=p_job AND epoch=policy.epoch AND (status='queued' OR status='running' AND lease_expires_at<now()) RETURNING * INTO j;
 IF j.id IS NULL THEN RETURN NULL; END IF;
 SELECT versions.* INTO v FROM app.document_versions versions JOIN app.documents d ON d.id=versions.document_id WHERE versions.id=j.document_version_id AND d.deleted_at IS NULL;
 IF v.id IS NULL THEN UPDATE app.guardrail_rescans SET status='cancelled',lease_expires_at=NULL WHERE id=p_job; RETURN NULL; END IF;
 RETURN to_jsonb(j)||jsonb_build_object('content_hash',v.content_hash,'configuration',v.configuration);
END $$""",
'app.guardrail_finish(uuid,uuid,jsonb)':r"""
CREATE FUNCTION app.guardrail_finish(p_job uuid,p_token uuid,p_assessment jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE; j app.guardrail_rescans%ROWTYPE; accepted boolean:=false;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 SELECT * INTO j FROM app.guardrail_rescans WHERE id=p_job AND epoch=policy.epoch AND rule_revision=policy.rule_revision
 AND status='running' AND lease_token=p_token AND lease_expires_at>now() FOR UPDATE;
 IF j.id IS NULL THEN RETURN false; END IF;
 IF p_assessment IS NOT NULL THEN accepted:=app.guardrail_store_assessment(j.document_version_id,p_assessment); END IF;
 UPDATE app.guardrail_rescans SET status=CASE WHEN accepted THEN 'completed' ELSE 'failed' END,lease_token=NULL,lease_expires_at=NULL WHERE id=p_job;
 IF NOT accepted THEN INSERT INTO app.guardrail_events(document_version_id,epoch,rule_revision,kind) VALUES(j.document_version_id,j.epoch,j.rule_revision,'scan_failed'); END IF;
 IF accepted THEN PERFORM app.wake_personal_waits(); END IF;
 RETURN accepted;
END $$""",
'app.guardrail_retry(uuid)':r"""
CREATE FUNCTION app.guardrail_retry(p_version uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 UPDATE app.guardrail_rescans SET status='queued',lease_token=NULL,lease_expires_at=NULL
 WHERE document_version_id=p_version AND epoch=policy.epoch AND status='failed';
 IF NOT FOUND THEN RETURN false; END IF;
 INSERT INTO app.guardrail_events(document_version_id,epoch,rule_revision,kind) VALUES(p_version,policy.epoch,policy.rule_revision,'retry');
 RETURN true;
END $$""",
'app.guardrail_review(uuid,text,text,bigint,boolean)':r"""
CREATE FUNCTION app.guardrail_review(p_version uuid,p_hash text,p_revision text,p_epoch bigint,p_public boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE policy app.guardrail_policy%ROWTYPE; a app.document_assessments%ROWTYPE; actor uuid;
BEGIN
 SELECT * INTO policy FROM app.guardrail_policy WHERE id=1 FOR SHARE;
 actor:=CASE WHEN p_public THEN '60000000-0000-4000-8000-000000000001'::uuid ELSE nullif(current_setting('docweave.actor_id',true),'')::uuid END;
 PERFORM d.id FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id JOIN app.collections c ON c.id=d.collection_id
 WHERE v.id=p_version AND d.deleted_at IS NULL AND
 ((NOT p_public AND app.personal_project_owned(c.project_id)) OR
 (p_public AND EXISTS(SELECT 1 FROM app.public_catalog_revisions r WHERE r.id=c.catalog_revision_id AND r.enabled AND r.source_approved))) FOR UPDATE OF d;
 IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 SELECT * INTO a FROM app.document_assessments WHERE document_version_id=p_version FOR UPDATE;
 IF a.document_version_id IS NULL OR p_hash IS DISTINCT FROM a.content_hash OR p_revision IS DISTINCT FROM policy.rule_revision
 OR a.rule_revision<>policy.rule_revision OR a.policy_epoch<>policy.epoch OR p_epoch IS DISTINCT FROM policy.epoch
 OR NOT a.complete OR a.credential_blocked OR NOT EXISTS(SELECT 1 FROM app.document_versions v WHERE v.id=p_version AND v.content_hash=a.content_hash
 AND a.parser_config_hash=encode(sha256(convert_to('{"configuration":'||to_json(v.configuration)::text||'}','UTF8')),'hex'))
 THEN RAISE EXCEPTION 'Review cannot waive block or stale assessment' USING ERRCODE='22023'; END IF;
 UPDATE app.document_assessments SET reviewed_by=actor WHERE document_version_id=p_version;
 INSERT INTO app.guardrail_events(document_version_id,epoch,rule_revision,kind,actor_id,findings) VALUES(p_version,policy.epoch,policy.rule_revision,'reviewed',actor,a.findings);
 PERFORM app.guardrail_restore_document(p_version);
 PERFORM app.wake_personal_waits();
 RETURN true;
END $$""",
'app.personal_review_document(uuid,uuid,text,text,bigint)':r"""
CREATE FUNCTION app.personal_review_document(p_document uuid,p_version uuid,p_hash text,p_revision text,p_epoch bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM app.document_versions WHERE document_id=p_document AND id=p_version) THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
 RETURN app.guardrail_review(p_version,p_hash,p_revision,p_epoch,false);
END $$""",
'app.review_guardrail_catalog(uuid,text,text,bigint)':r"""
CREATE FUNCTION app.review_guardrail_catalog(p_version uuid,p_hash text,p_revision text,p_epoch bigint) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT app.guardrail_review(p_version,p_hash,p_revision,p_epoch,true)
$$""",
}

# Existing publication functions keep their current behavior and acquire a policy share
# lock before checking eligibility, serializing publication against rule activation.
FENCES={
 'app.index_input(uuid,uuid)': 'BEGIN',
 'app.catalog_index_input(uuid,uuid)': 'BEGIN',
 'app.personal_finish_job(uuid,uuid,jsonb)': 'BEGIN',
 'app.personal_worker_summary(uuid,uuid,integer,jsonb)': 'BEGIN',
}

CHANGES=(
 ('app.catalog_entries(uuid)',
  "WHEN j.status IN ('queued','running') THEN 'processing'",
  "WHEN guard.state IS NOT NULL THEN guard.state\n WHEN j.status IN ('queued','running') THEN 'processing'"),
 ('app.catalog_entries(uuid)',
  "r.source_approved AND coalesce(j.status IN ('queued','running'),false)",
  "r.source_approved AND (guard.state='processing' OR coalesce(j.status IN ('queued','running'),false))"),
 ('app.catalog_entries(uuid)',
  'WHERE r.enabled ORDER BY r.technology,r.id',
  "LEFT JOIN LATERAL(SELECT app.guardrail_document_state(d.active_version_id) state FROM app.collections c JOIN app.documents d ON d.collection_id=c.id WHERE c.catalog_revision_id=r.id AND d.deleted_at IS NULL ORDER BY d.id LIMIT 1) guard ON true\n WHERE r.enabled ORDER BY r.technology,r.id"),
 ('app.personal_private_source_entries(uuid,uuid)',
  "WHEN d.active_version_id IS NOT NULL AND NOT app.personal_assessment_eligible(d.active_version_id) THEN 'pending_review'",
  "WHEN app.guardrail_document_state(d.active_version_id) IS NOT NULL THEN app.guardrail_document_state(d.active_version_id)"),
 ('app.personal_private_source_entries(uuid,uuid)',
  "'active_job',activity.value",
  "'active_job',activity.value OR app.guardrail_document_state(d.active_version_id)='processing'"),
 ('app.personal_citations_current(uuid,jsonb)',
  'AND app.personal_assessment_eligible(ch.document_version_id)',
  "AND app.personal_assessment_eligible(ch.document_version_id) AND (c.catalog_revision_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM app.index_generations g CROSS JOIN LATERAL jsonb_array_elements_text(g.processor_ids) wanted(id) LEFT JOIN app.processors processor ON processor.id=wanted.id WHERE g.id=ch.generation_id AND (processor.id IS NULL OR NOT processor.enabled OR NOT EXISTS(SELECT 1 FROM app.project_processor_approvals approval WHERE approval.project_id=p_project AND approval.processor_id=wanted.id) OR NOT EXISTS(SELECT 1 FROM app.collection_processor_approvals approval WHERE approval.collection_id=c.id AND approval.processor_id=wanted.id))))"),
 ('app.personal_worker_summary(uuid,uuid,integer,jsonb)',
  "(c.summary->>'context_revision')::integer=p_revision",
  "(c.summary->>'context_revision')::integer=p_revision AND c.summary->>'policy_epoch'=(SELECT epoch::text FROM app.guardrail_policy WHERE id=1) AND NOT EXISTS(SELECT 1 FROM app.turns t WHERE t.conversation_id=c.id AND t.sequence<=(c.summary->>'through_sequence')::integer AND app.personal_turn(t.id)->>'status'='blocked_policy')"),
 ('app.personal_worker_summary(uuid,uuid,integer,jsonb)',
  " IF jsonb_typeof(p_summary)<>'object'",
  " IF p_summary->>'policy_epoch' IS DISTINCT FROM (SELECT epoch::text FROM app.guardrail_policy WHERE id=1) THEN RETURN NULL; END IF;\n IF jsonb_typeof(p_summary)<>'object'"),
 ('app.personal_finish_job(uuid,uuid,jsonb)',
  ' ELSE\n  IF coalesce',
  " ELSE\n  IF p_result ? 'expected_policy_epoch' AND p_result->>'expected_policy_epoch' IS DISTINCT FROM (SELECT epoch::text FROM app.guardrail_policy WHERE id=1) THEN p_result:=jsonb_build_object('status','blocked_policy','progress','Guardrail policy changed before release.'); END IF;\n  IF coalesce"),
)


def definition(signature):
    return op.get_bind().scalar(sa.text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'),{'signature':signature})


def change_functions(reverse=False):
    definitions={}
    for signature,before,after in reversed(CHANGES) if reverse else CHANGES:
        sql=definitions.get(signature) or definition(signature)
        if not reverse and before not in sql:
            raise ValueError('Unexpected guardrail publication function')
        definitions[signature]=sql.replace(after,before,1) if reverse else sql.replace(before,after,1)
    for sql in definitions.values():
        op.execute(sql)


def upgrade():
    op.create_table('guardrail_policy',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('rule_revision',sa.Text(),nullable=False),sa.Column('epoch',sa.BigInteger(),nullable=False),sa.CheckConstraint('id=1',name='singleton'),schema='app')
    op.execute(sa.text('INSERT INTO app.guardrail_policy VALUES(1,:revision,1)').bindparams(revision=INITIAL_REVISION))
    op.add_column('document_assessments',sa.Column('policy_epoch',sa.BigInteger(),nullable=False,server_default='0'),schema='app')
    op.add_column('document_assessments',sa.Column('findings',JSONB(),nullable=False,server_default='[]'),schema='app')
    for table in ('guardrail_rescans','guardrail_events'):
        columns=[sa.Column('id',sa.UUID(),primary_key=True,server_default=sa.text('gen_random_uuid()')),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
            sa.Column('document_version_id',sa.UUID(),sa.ForeignKey('app.document_versions.id',ondelete='RESTRICT'),nullable=table=='guardrail_events'),sa.Column('epoch',sa.BigInteger(),nullable=False)]
        if table=='guardrail_rescans':
            columns += [sa.Column('rule_revision',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False,server_default='queued'),sa.Column('lease_token',sa.UUID()),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),sa.UniqueConstraint('document_version_id','epoch',name='uq_guardrail_rescan_epoch')]
        else:
            columns += [sa.Column('rule_revision',sa.Text(),nullable=False),sa.Column('kind',sa.Text(),nullable=False),sa.Column('actor_id',sa.UUID(),sa.ForeignKey('app.users.id',ondelete='RESTRICT')),sa.Column('findings',JSONB(),nullable=False,server_default='[]')]
        op.create_table(table,*columns,schema='app')
    for table in ('guardrail_policy','guardrail_rescans','guardrail_events'):
        op.execute(f'ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime,docweave_worker')
    for signature,sql in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,docweave_runtime,docweave_worker')
        if signature.startswith('app.guardrail_fence'):
            op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime,docweave_worker')
        elif signature.startswith(('app.personal_review_document','app.personal_assessment_view','app.personal_version_assessment_view')):
            op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_runtime')
        elif signature.startswith(('app.guardrail_reconcile','app.guardrail_claim','app.guardrail_finish','app.assess_ingestion_version')):
            op.execute(f'GRANT EXECUTE ON FUNCTION {signature} TO docweave_worker')
    op.execute('DROP FUNCTION app.personal_review_document(uuid,uuid,text,text)')
    for signature,marker in FENCES.items():
        sql=definition(signature)
        op.execute(sql.replace(marker,marker+'\n PERFORM id FROM app.guardrail_policy WHERE id=1 FOR SHARE;',1))
    change_functions()
    sql=definition('app.publish_catalog_snapshot(uuid,uuid,uuid,jsonb,jsonb)')
    sql=sql.replace("p_assessment->>'rule_revision'<>'deterministic-v1'","p_assessment->>'rule_revision' IS DISTINCT FROM (SELECT rule_revision FROM app.guardrail_policy WHERE id=1)")
    start=sql.index(' INSERT INTO app.document_assessments(')
    end=sql.index('\n UPDATE app.documents',start)
    sql=sql[:start]+" IF NOT app.guardrail_store_assessment(p_version,p_assessment) THEN RAISE EXCEPTION 'Assessment mismatch' USING ERRCODE='22023'; END IF;"+sql[end:]
    op.execute(sql.replace('BEGIN','BEGIN\n PERFORM id FROM app.guardrail_policy WHERE id=1 FOR SHARE;',1))


def downgrade():
    # Retain the audit trail and epoch fence once any lifecycle work has occurred.
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.guardrail_events) OR EXISTS(SELECT 1 FROM app.guardrail_rescans) THEN RAISE EXCEPTION 'Preserve guardrail audit and rescan state before downgrade'; END IF; END $$")
    import importlib.util
    from pathlib import Path
    def prior(name):
        spec=importlib.util.spec_from_file_location('guardrail_previous_'+name,Path(__file__).with_name(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    change_functions(reverse=True)
    for signature in FENCES:
        op.execute(definition(signature).replace('\n PERFORM id FROM app.guardrail_policy WHERE id=1 FOR SHARE;','',1))
    signature='app.publish_catalog_snapshot(uuid,uuid,uuid,jsonb,jsonb)'
    sql=prior('0019_shared_ingestion').FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
    for changed,before,after in prior('0035_source_media').CHANGES:
        if changed==signature:
            sql=sql.replace(before,after)
    op.execute(sql)
    for name,signature in [('0024_personal_private_knowledge','app.assess_ingestion_version(uuid,jsonb)'),('0017_personal_retrieval','app.personal_assessment_eligible(uuid)'),('0025_personal_guardrail_review','app.personal_assessment_view(uuid)')]:
        sql=prior(name).FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
        if signature.startswith('app.assess_ingestion_version'):
            sql=sql.replace('reviewed_by=NULL;',"reviewed_by=CASE WHEN (app.document_assessments.content_hash,app.document_assessments.parser_config_hash,app.document_assessments.rule_revision) IS NOT DISTINCT FROM (excluded.content_hash,excluded.parser_config_hash,excluded.rule_revision) THEN app.document_assessments.reviewed_by ELSE NULL END;")
        op.execute(sql)
    for signature in reversed(FUNCTIONS):
        if signature not in ('app.personal_assessment_eligible(uuid)','app.assess_ingestion_version(uuid,jsonb)','app.personal_assessment_view(uuid)'):
            op.execute(f'DROP FUNCTION IF EXISTS {signature}')
    op.execute(prior('0024_personal_private_knowledge').FUNCTIONS['app.personal_review_document(uuid,uuid,text,text)'])
    op.execute('REVOKE ALL ON FUNCTION app.personal_review_document(uuid,uuid,text,text) FROM PUBLIC,docweave_worker')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_review_document(uuid,uuid,text,text) TO docweave_runtime')
    for table in ('guardrail_events','guardrail_rescans','guardrail_policy'):
        op.drop_table(table,schema='app')
    op.drop_column('document_assessments','findings',schema='app')
    op.drop_column('document_assessments','policy_epoch',schema='app')
