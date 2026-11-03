"""Drain overdue retained payloads before traffic, including old paid checkpoints."""
import importlib.util
from pathlib import Path
from alembic import op

revision = '0045_retention_acceptance'
down_revision = '0044_retire_product_rpcs'
branch_labels = None
depends_on = None

# shortcut: stage names mirror admitted job keys; extend with any new paid stage.
STAGES = "('summarization'),('query_resolution'),('query_embedding'),('reranking'),('generation')"
MATCH = "calls.key_hash=encode(sha256(convert_to(j.id::text||':'||stage.name,'UTF8')),'hex')"
PAYLOAD = f"""(c.summary IS NOT NULL OR c.progress IS NOT NULL OR EXISTS(
 SELECT 1 FROM app.turns t WHERE t.conversation_id=c.id AND
 (t.message<>'' OR t.answer IS NOT NULL OR t.citations<>'[]'::jsonb OR t.required_dependencies<>'[]'::jsonb OR t.progress IS NOT NULL))
 OR EXISTS(SELECT 1 FROM app.personal_jobs j JOIN app.personal_provider_calls calls ON calls.response IS NOT NULL
 CROSS JOIN (VALUES {STAGES}) stage(name) WHERE j.conversation_id=c.id AND {MATCH}))"""

CLEANUP = f"""
CREATE OR REPLACE FUNCTION app.personal_cleanup_deleted_conversations(p_id uuid) RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 WITH candidates AS MATERIALIZED (
  SELECT c.id FROM app.conversations c WHERE c.deleted_at IS NOT NULL AND (p_id IS NULL OR c.id=p_id)
  AND {PAYLOAD} ORDER BY c.deleted_at,c.id LIMIT 100 FOR UPDATE OF c SKIP LOCKED
 ), erased_turns AS (
  UPDATE app.turns t SET message='',answer=NULL,citations='[]',required_dependencies='[]',progress=NULL
  FROM candidates c WHERE t.conversation_id=c.id RETURNING t.id
 ), erased_calls AS (
  UPDATE app.personal_provider_calls calls SET response=NULL WHERE calls.response IS NOT NULL AND EXISTS(
   SELECT 1 FROM app.personal_jobs j JOIN candidates c ON c.id=j.conversation_id
   CROSS JOIN (VALUES {STAGES}) stage(name) WHERE {MATCH}) RETURNING calls.operation_hash
 ), erased_chats AS (
  UPDATE app.conversations c SET summary=NULL,progress=NULL FROM candidates d WHERE c.id=d.id RETURNING c.id
 ) SELECT count(*)::integer FROM erased_chats
$$
"""

DOCUMENT_PAYLOAD = """(d.title<>'Deleted document' OR EXISTS(
 SELECT 1 FROM app.private_index_jobs j WHERE j.document_id=d.id AND j.status<>'deleted'))"""

PRIVATE_CHECKPOINTS = """
CREATE FUNCTION app.erase_private_index_responses(p_document uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 UPDATE app.personal_provider_calls calls SET response=NULL WHERE calls.response IS NOT NULL AND calls.key_hash IN (
  SELECT encode(sha256(convert_to('private-index:'||j.id::text||':'||ordinal.n::text,'UTF8')),'hex')
  FROM app.private_index_jobs j CROSS JOIN generate_series(0,9999) ordinal(n) WHERE j.document_id=p_document);
 UPDATE app.private_index_jobs SET status='deleted',lease_token=NULL,lease_expires_at=NULL,key_hash=NULL WHERE document_id=p_document;
END $$
"""

DELETED_ARTIFACTS = """
CREATE FUNCTION app.deleted_ingestion_artifacts() RETURNS TABLE(id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT v.id FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id WHERE d.deleted_at IS NOT NULL
 UNION SELECT j.id FROM app.ingestion_jobs j JOIN app.documents d ON d.id=j.document_id WHERE d.deleted_at IS NOT NULL
$$
"""

DOCUMENT_CLEANUP = f"""
CREATE FUNCTION app.personal_cleanup_deleted_documents(p_document uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE identity uuid; erased integer:=0;
BEGIN
 FOR identity IN SELECT d.id FROM app.documents d WHERE d.deleted_at IS NOT NULL
 AND (p_document IS NULL OR d.id=p_document) AND {DOCUMENT_PAYLOAD}
 ORDER BY d.deleted_at,d.id LIMIT 100 FOR UPDATE OF d SKIP LOCKED LOOP
  PERFORM app.erase_private_index_responses(identity);
  UPDATE app.documents SET title='Deleted document' WHERE id=identity;
  erased:=erased+1;
 END LOOP;
 RETURN erased;
END $$
"""

DOCUMENT_TRIGGER = """
CREATE FUNCTION app.erase_deleted_document_payload() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
BEGIN
 IF NEW.deleted_at IS NOT NULL THEN
  PERFORM app.erase_private_index_responses(NEW.id);
  NEW.title:='Deleted document';
 END IF;
 RETURN NEW;
END $$
"""

OVERDUE = f"""
CREATE FUNCTION app.retention_overdue() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT EXISTS(SELECT 1 FROM app.conversations c WHERE c.deleted_at<=now()-interval '1 day' AND {PAYLOAD})
 OR EXISTS(SELECT 1 FROM app.documents d WHERE d.deleted_at<=now()-interval '1 day' AND {DOCUMENT_PAYLOAD})
 OR EXISTS(SELECT 1 FROM app.auth_flows WHERE expires_at<=now()-interval '1 day')
 OR EXISTS(SELECT 1 FROM app.auth_sessions WHERE expires_at<=now()-interval '1 day')
 OR EXISTS(SELECT 1 FROM app.auth_rate_limits WHERE resets_at<=now()-interval '1 day')
$$
"""

LOCK_INDEX_JOBS = '    PERFORM j.id FROM app.private_index_jobs j WHERE j.document_id=p_document ORDER BY j.id FOR UPDATE;\n'
ARTIFACT_SELECTION = "    SELECT coalesce(jsonb_agg(id),'[]'::jsonb) INTO artifacts FROM ("
RECOVERY = ' PERFORM app.personal_cleanup_deleted_conversations(NULL);'


def change(signature, before, after):
    from sqlalchemy import text
    definition = op.get_bind().scalar(text('SELECT pg_get_functiondef(CAST(:signature AS regprocedure))'), {'signature': signature})
    if before not in definition:
        raise ValueError('Unexpected retention function definition')
    op.execute(definition.replace(before, after, 1))


def upgrade():
    op.execute(CLEANUP)
    # shortcut: enumerate the 10,000 admitted private chunk ordinals; update with any parser-limit increase.
    op.execute(PRIVATE_CHECKPOINTS)
    op.execute(DOCUMENT_CLEANUP)
    op.execute(DOCUMENT_TRIGGER)
    op.execute(DELETED_ARTIFACTS)
    for signature in ('app.erase_private_index_responses(uuid)', 'app.personal_cleanup_deleted_documents(uuid)', 'app.erase_deleted_document_payload()'):
        op.execute('REVOKE ALL ON FUNCTION '+signature+' FROM PUBLIC,docweave_runtime,docweave_worker')
    op.execute('GRANT EXECUTE ON FUNCTION app.personal_cleanup_deleted_documents(uuid) TO docweave_worker')
    op.execute('REVOKE ALL ON FUNCTION app.deleted_ingestion_artifacts() FROM PUBLIC,docweave_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION app.deleted_ingestion_artifacts() TO docweave_worker')
    change('app.delete_ingestion_document(uuid)', ARTIFACT_SELECTION, LOCK_INDEX_JOBS+ARTIFACT_SELECTION)
    op.execute('CREATE TRIGGER erase_deleted_document_payload BEFORE UPDATE OF deleted_at ON app.documents FOR EACH ROW EXECUTE FUNCTION app.erase_deleted_document_payload()')
    change('app.personal_recover_jobs()', RECOVERY, RECOVERY+'\n PERFORM app.personal_cleanup_deleted_documents(NULL);')
    op.execute(OVERDUE)
    op.execute('REVOKE ALL ON FUNCTION app.retention_overdue() FROM PUBLIC')
    op.execute('GRANT EXECUTE ON FUNCTION app.retention_overdue() TO docweave_runtime,docweave_worker')


def downgrade():
    op.execute('DROP FUNCTION app.retention_overdue()')
    change('app.personal_recover_jobs()', RECOVERY+'\n PERFORM app.personal_cleanup_deleted_documents(NULL);', RECOVERY)
    op.execute('DROP TRIGGER erase_deleted_document_payload ON app.documents')
    op.execute('DROP FUNCTION app.erase_deleted_document_payload()')
    change('app.delete_ingestion_document(uuid)', LOCK_INDEX_JOBS, '')
    op.execute('DROP FUNCTION app.personal_cleanup_deleted_documents(uuid)')
    op.execute('DROP FUNCTION app.erase_private_index_responses(uuid)')
    op.execute('DROP FUNCTION app.deleted_ingestion_artifacts()')
    spec = importlib.util.spec_from_file_location('retention_prior', Path(__file__).with_name('0041_chat_cleanup.py'))
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    op.execute(prior.FUNCTION.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1))
