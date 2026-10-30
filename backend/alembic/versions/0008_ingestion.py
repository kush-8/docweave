"""Durable text snapshots and a separate Procrastinate ingestion service role."""

from importlib.resources import files

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_ingestion"
down_revision = "0007_budget"
branch_labels = None
depends_on = None


def record():
    return [sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def col(name, kind=sa.UUID, *, nullable=False, default=None):
    return sa.Column(name, kind(), nullable=nullable, server_default=default)


def upgrade():
    op.execute("SET LOCAL search_path=queue,pg_catalog")
    # This schema is pinned by uv.lock; upgrades require a new explicit migration.
    raw = op.get_bind().connection.dbapi_connection
    raw.run_async(lambda connection: connection.execute((files("procrastinate.sql") / "schema.sql").read_text(encoding="utf-8")))
    op.execute("SET LOCAL search_path=pg_catalog,app")
    op.execute("REVOKE ALL ON SCHEMA queue FROM PUBLIC,docweave_runtime")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA queue FROM PUBLIC,docweave_runtime")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA queue FROM PUBLIC,docweave_runtime")
    op.execute("GRANT USAGE ON SCHEMA queue TO docweave_worker")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA queue TO docweave_worker")
    op.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA queue TO docweave_worker")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA queue TO docweave_worker")
    op.create_table("documentation_selections", *record(), col("workspace_id"), col("project_id"), col("approved_by"),
        col("technology", sa.Text), col("docs_target", sa.Text), col("coverage", JSONB), col("source_url", sa.Text),
        col("origin", sa.Text), col("path_prefix", sa.Text), col("attribution", sa.Text), col("active", sa.Boolean, default=sa.text("true")),
        sa.ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["app.users.id"], ondelete="RESTRICT"), schema="app")
    op.create_table("sources", *record(), col("workspace_id"), col("collection_id"), col("source_selection_id"), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_selection_id"], ["app.documentation_selections.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("collection_id", "source_selection_id", name="uq_sources_selection"), schema="app")
    op.create_table("documents", *record(), col("workspace_id"), col("collection_id"), col("source_id", nullable=True),
        col("title", sa.Text), col("media_type", sa.Text), col("status", sa.Text, default=sa.text("'quarantined'")),
        col("active_version_id", nullable=True), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["app.sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"), schema="app")
    op.create_table("document_versions", *record(), col("workspace_id"), col("document_id"), col("content_hash", sa.Text),
        col("configuration", sa.Text), col("source_url", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("document_id", "content_hash", "configuration", name="uq_document_versions_content"), schema="app")
    op.create_table("ingestion_jobs", *record(), col("workspace_id"), col("document_id"), col("actor_id"), col("kind", sa.Text), col("media_type", sa.Text),
        col("input_hash", sa.Text), col("configuration", sa.Text), col("request_id"),
        col("status", sa.Text, default=sa.text("'queued'")), col("stage", sa.Text, default=sa.text("'quarantined'")),
        col("attempts", sa.Integer, default=sa.text("0")), col("retryable", sa.Boolean, default=sa.text("false")),
        col("lease_token", nullable=True), sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app.users.id"], ondelete="RESTRICT"), schema="app")
    for table in TABLES:
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON app.{table} FROM PUBLIC,docweave_runtime,docweave_worker")
    op.execute("GRANT SELECT ON app.documents,app.sources TO docweave_runtime")
    for table in ("documents", "sources"):
        op.execute(f"CREATE POLICY runtime_read ON app.{table} FOR SELECT TO docweave_runtime USING (deleted_at IS NULL AND app.collection_can(collection_id,'read'))")
    for statement in FUNCTIONS.values():
        op.execute(statement)
    op.execute("CREATE TRIGGER immutable_selection BEFORE UPDATE OR DELETE ON app.documentation_selections FOR EACH ROW EXECUTE FUNCTION app.immutable_selection()")
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        role = "docweave_worker" if signature.split("(")[0] in WORKER_FUNCTIONS else "docweave_runtime"
        if signature != "app.immutable_selection()":
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


TABLES = ("documentation_selections", "sources", "documents", "document_versions", "ingestion_jobs")
WORKER_FUNCTIONS = {"app.claim_ingestion", "app.publish_ingestion", "app.fail_ingestion", "app.ingestion_artifacts", "app.ingestion_authorized", "app.ingestion_recoverable"}
FUNCTIONS = {
"app.immutable_selection()": """
CREATE FUNCTION app.immutable_selection() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
BEGIN
    IF TG_OP='DELETE' OR (to_jsonb(NEW)-'active') IS DISTINCT FROM (to_jsonb(OLD)-'active') THEN
        RAISE EXCEPTION 'Selection identity is immutable' USING ERRCODE='22023';
    END IF;
    RETURN NEW;
END $$
""",
"app.ingestion_resource(text,uuid)": """
CREATE FUNCTION app.ingestion_resource(p_kind text,p_id uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT app.collection_workspace(d.collection_id) FROM app.documents d
    WHERE d.deleted_at IS NULL AND ((p_kind='document' AND d.id=p_id)
        OR (p_kind='job' AND EXISTS (SELECT 1 FROM app.ingestion_jobs j WHERE j.id=p_id AND j.document_id=d.id))
        OR (p_kind='source' AND d.source_id=p_id AND EXISTS (SELECT 1 FROM app.sources s WHERE s.id=p_id AND s.deleted_at IS NULL)))
    LIMIT 1
$$
""",
"app.selection_for_import(uuid,uuid)": """
CREATE FUNCTION app.selection_for_import(p_selection uuid,p_collection uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT to_jsonb(ds) FROM app.documentation_selections ds JOIN app.collections c ON c.project_id=ds.project_id AND c.workspace_id=ds.workspace_id
    WHERE ds.id=p_selection AND ds.active AND c.id=p_collection AND app.collection_can(c.id,'write')
$$
""",
"app.sources_view()": """
CREATE FUNCTION app.sources_view() RETURNS TABLE(id uuid,created_at timestamptz,project_id uuid,collection_id uuid,source_selection_id uuid,
    technology text,declared_version text,resolved_version text,docs_target text,coverage jsonb,status text,accepted_pages integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT s.id,s.created_at,c.project_id,s.collection_id,s.source_selection_id,ds.technology,NULL::text,NULL::text,ds.docs_target,ds.coverage,
        CASE WHEN d.status='quarantined' THEN 'queued' ELSE d.status END,
        CASE WHEN d.active_version_id IS NULL THEN 0 ELSE 1 END
    FROM app.sources s JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
    JOIN app.collections c ON c.id=s.collection_id JOIN app.documents d ON d.source_id=s.id
    WHERE s.deleted_at IS NULL AND d.deleted_at IS NULL AND app.collection_can(s.collection_id,'read')
$$
""",
"app.delete_ingestion_source(uuid)": """
CREATE FUNCTION app.delete_ingestion_source(p_source uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE d uuid; result jsonb;
BEGIN
    PERFORM 1 FROM app.workspaces WHERE id=nullif(current_setting('docweave.workspace_id',true),'')::uuid FOR UPDATE;
    SELECT doc.id INTO d FROM app.documents doc JOIN app.sources s ON s.id=doc.source_id WHERE s.id=p_source AND s.deleted_at IS NULL AND doc.deleted_at IS NULL;
    IF d IS NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
    result := app.delete_ingestion_document(d);
    UPDATE app.sources SET deleted_at=clock_timestamp() WHERE id=p_source;
    RETURN result;
END $$
""",
"app.enqueue_ingestion(uuid,uuid,uuid,text,text,text,text,uuid,uuid)": """
CREATE FUNCTION app.enqueue_ingestion(p_job uuid,p_collection uuid,p_document uuid,p_title text,p_media text,
    p_hash text,p_config text,p_request uuid,p_selection uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,queue AS $$
DECLARE w uuid := nullif(current_setting('docweave.workspace_id',true),'')::uuid;
    actor uuid := nullif(current_setting('docweave.actor_id',true),'')::uuid;
    d app.documents%ROWTYPE; j app.ingestion_jobs%ROWTYPE; selection app.documentation_selections%ROWTYPE;
    source app.sources%ROWTYPE; kind text; queue_id bigint;
BEGIN
    PERFORM 1 FROM app.workspaces WHERE id=w FOR UPDATE;
    IF NOT app.collection_can(p_collection,'read') THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
    IF NOT app.collection_can(p_collection,'write') THEN RAISE EXCEPTION 'Forbidden' USING ERRCODE='42501'; END IF;
    IF p_title IS NULL OR length(p_title) NOT BETWEEN 1 AND 200 OR p_media NOT IN ('text/plain','text/markdown')
        OR p_hash !~ '^[0-9a-f]{64}$' OR p_config IS DISTINCT FROM ('utf8-lf:headings:whitespace350-overlap50:v1:'||p_media) THEN
        RAISE EXCEPTION 'Invalid input' USING ERRCODE='22023'; END IF;
    IF p_selection IS NOT NULL THEN
        SELECT ds.* INTO selection FROM app.documentation_selections ds JOIN app.collections c ON c.project_id=ds.project_id
            WHERE ds.id=p_selection AND ds.workspace_id=w AND c.id=p_collection AND ds.active;
        IF NOT FOUND THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
        INSERT INTO app.sources(workspace_id,collection_id,source_selection_id) VALUES(w,p_collection,p_selection)
            ON CONFLICT(collection_id,source_selection_id) DO NOTHING;
        SELECT * INTO source FROM app.sources WHERE collection_id=p_collection AND source_selection_id=p_selection;
        IF source.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
        SELECT * INTO d FROM app.documents WHERE source_id=source.id AND deleted_at IS NULL;
        kind := CASE WHEN d.id IS NULL THEN 'import' ELSE 'refresh' END;
    ELSIF p_document IS NOT NULL THEN
        SELECT * INTO d FROM app.documents WHERE id=p_document AND collection_id=p_collection AND deleted_at IS NULL;
        IF NOT FOUND OR d.source_id IS NOT NULL THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
        kind := 'replace';
    ELSE
        SELECT doc.* INTO d FROM app.documents doc JOIN app.ingestion_jobs old ON old.document_id=doc.id
            WHERE doc.collection_id=p_collection AND doc.source_id IS NULL AND doc.deleted_at IS NULL
                AND old.input_hash=p_hash AND old.configuration=p_config AND doc.title=p_title ORDER BY old.created_at DESC LIMIT 1;
        kind := 'upload';
    END IF;
    IF d.id IS NULL THEN
        INSERT INTO app.documents(workspace_id,collection_id,source_id,title,media_type)
            VALUES(w,p_collection,source.id,p_title,p_media) RETURNING * INTO d;
    END IF;
    SELECT * INTO j FROM app.ingestion_jobs WHERE document_id=d.id AND input_hash=p_hash AND configuration=p_config
        AND status NOT IN ('failed','blocked_policy') ORDER BY created_at DESC LIMIT 1;
    IF FOUND AND (j.status IN ('queued','running') OR (p_selection IS NULL AND p_document IS NULL)) THEN
        RETURN jsonb_build_object('document_id',d.id,'job_id',j.id);
    END IF;
    IF EXISTS (SELECT 1 FROM app.ingestion_jobs WHERE document_id=d.id AND status IN ('queued','running')) THEN
        RAISE EXCEPTION 'Another ingestion is active' USING ERRCODE='DW004'; END IF;
    INSERT INTO app.ingestion_jobs(id,workspace_id,document_id,actor_id,kind,media_type,input_hash,configuration,request_id)
        VALUES(p_job,w,d.id,actor,kind,p_media,p_hash,p_config,p_request);
    SELECT unnest(queue.procrastinate_defer_jobs_v1(ARRAY[ROW('ingestion','docweave.ingest',0,'ingestion',NULL,
        jsonb_build_object('job_id',p_job),NULL::timestamptz)]::queue.procrastinate_job_to_defer_v1[])) INTO queue_id;
    RETURN jsonb_build_object('document_id',d.id,'job_id',p_job);
END $$
""",
"app.document_versions_view(uuid)": """
CREATE FUNCTION app.document_versions_view(p_document uuid) RETURNS TABLE(id uuid,document_id uuid,captured_at timestamptz,active boolean,index_configuration_id text,source_url text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT v.id,v.document_id,v.created_at,v.id=d.active_version_id,v.configuration,v.source_url
    FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id
    WHERE d.id=p_document AND d.deleted_at IS NULL AND app.collection_can(d.collection_id,'read')
$$
""",
"app.ingestion_jobs_view()": """
CREATE FUNCTION app.ingestion_jobs_view() RETURNS TABLE(id uuid,document_id uuid,collection_id uuid,project_id uuid,kind text,status text,attempts integer,retryable boolean,request_id uuid,stage text,created_at timestamptz,finished_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT j.id,j.document_id,d.collection_id,c.project_id,j.kind,j.status,j.attempts,j.retryable,j.request_id,j.stage,j.created_at,j.finished_at
    FROM app.ingestion_jobs j JOIN app.documents d ON d.id=j.document_id JOIN app.collections c ON c.id=d.collection_id
    WHERE d.deleted_at IS NULL AND app.collection_can(d.collection_id,'read')
$$
""",
"app.delete_ingestion_document(uuid)": """
CREATE FUNCTION app.delete_ingestion_document(p_document uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE d app.documents%ROWTYPE; artifacts jsonb;
BEGIN
    PERFORM 1 FROM app.workspaces WHERE id=nullif(current_setting('docweave.workspace_id',true),'')::uuid FOR UPDATE;
    SELECT * INTO d FROM app.documents WHERE id=p_document AND deleted_at IS NULL;
    IF NOT FOUND OR NOT app.collection_can(d.collection_id,'read') THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
    IF NOT app.collection_can(d.collection_id,'write') THEN RAISE EXCEPTION 'Forbidden' USING ERRCODE='42501'; END IF;
    SELECT coalesce(jsonb_agg(id),'[]'::jsonb) INTO artifacts FROM (
        SELECT id FROM app.document_versions WHERE document_id=d.id UNION SELECT id FROM app.ingestion_jobs WHERE document_id=d.id) all_ids;
    UPDATE app.documents SET deleted_at=clock_timestamp(),active_version_id=NULL WHERE id=d.id;
    UPDATE app.sources SET deleted_at=clock_timestamp() WHERE id=d.source_id;
    UPDATE app.ingestion_jobs SET status='blocked_policy',lease_token=NULL,lease_until=NULL,finished_at=clock_timestamp() WHERE document_id=d.id;
    RETURN jsonb_build_object('deletion_id',d.id,'access_removed',true,'accepted_at',clock_timestamp(),'artifacts',artifacts);
END $$
""",
"app.claim_ingestion(uuid)": """
CREATE FUNCTION app.claim_ingestion(p_job uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.ingestion_jobs%ROWTYPE; d app.documents%ROWTYPE; sel app.documentation_selections%ROWTYPE;
BEGIN
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job;
    IF NOT FOUND THEN RETURN NULL; END IF;
    PERFORM 1 FROM app.workspaces WHERE id=j.workspace_id FOR UPDATE;
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job FOR UPDATE;
    IF j.status IN ('completed','failed','blocked_policy') OR (j.status='running' AND j.lease_until>clock_timestamp()) THEN RETURN NULL; END IF;
    PERFORM set_config('docweave.actor_id',j.actor_id::text,true),set_config('docweave.workspace_id',j.workspace_id::text,true);
    SELECT * INTO d FROM app.documents WHERE id=j.document_id;
    IF d.source_id IS NOT NULL THEN
        SELECT ds.* INTO sel FROM app.documentation_selections ds JOIN app.sources s ON s.source_selection_id=ds.id
            WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active;
    END IF;
    IF d.deleted_at IS NOT NULL OR NOT app.collection_can(d.collection_id,'write') OR (d.source_id IS NOT NULL AND sel.id IS NULL) THEN
        UPDATE app.ingestion_jobs SET status='blocked_policy',finished_at=clock_timestamp(),lease_token=NULL WHERE id=j.id;
        RETURN NULL;
    END IF;
    IF j.attempts>=3 THEN
        UPDATE app.ingestion_jobs SET status='failed',retryable=false,finished_at=clock_timestamp() WHERE id=j.id; RETURN NULL;
    END IF;
    UPDATE app.ingestion_jobs SET status='running',stage='preparing',attempts=attempts+1,
        lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '120 seconds' WHERE id=j.id RETURNING * INTO j;
    RETURN jsonb_build_object('id',j.id,'token',j.lease_token,'document_id',d.id,'media_type',j.media_type,'selection',
        CASE WHEN sel.id IS NULL THEN NULL ELSE to_jsonb(sel) END);
END $$
""",
"app.publish_ingestion(uuid,uuid,uuid,text,text)": """
CREATE FUNCTION app.publish_ingestion(p_job uuid,p_token uuid,p_version uuid,p_hash text,p_config text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.ingestion_jobs%ROWTYPE; d app.documents%ROWTYPE; selected uuid; link text; doc_status text;
BEGIN
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job;
    IF NOT FOUND THEN RETURN NULL; END IF;
    PERFORM 1 FROM app.workspaces WHERE id=j.workspace_id FOR UPDATE;
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job FOR UPDATE;
    IF j.status<>'running' OR j.lease_token IS DISTINCT FROM p_token THEN RETURN NULL; END IF;
    IF j.lease_until<=clock_timestamp() THEN
        UPDATE app.ingestion_jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,
            stage='lease_expired',retryable=attempts<3,lease_token=NULL,lease_until=NULL,
            finished_at=CASE WHEN attempts<3 THEN NULL ELSE clock_timestamp() END WHERE id=j.id;
        RETURN jsonb_build_object('retry',j.attempts<3);
    END IF;
    PERFORM set_config('docweave.actor_id',j.actor_id::text,true),set_config('docweave.workspace_id',j.workspace_id::text,true);
    SELECT * INTO d FROM app.documents WHERE id=j.document_id;
    IF d.source_id IS NOT NULL THEN
        SELECT ds.source_url INTO link FROM app.sources s JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
            WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active;
    END IF;
    IF d.deleted_at IS NOT NULL OR NOT app.collection_can(d.collection_id,'write') OR (d.source_id IS NOT NULL AND link IS NULL) THEN
        UPDATE app.ingestion_jobs SET status='blocked_policy',lease_token=NULL,finished_at=clock_timestamp() WHERE id=j.id; RETURN NULL;
    END IF;
    IF p_config IS DISTINCT FROM j.configuration OR p_hash !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Invalid snapshot' USING ERRCODE='22023'; END IF;
    INSERT INTO app.document_versions(id,workspace_id,document_id,content_hash,configuration,source_url)
        VALUES(p_version,j.workspace_id,d.id,p_hash,p_config,link) ON CONFLICT(document_id,content_hash,configuration) DO NOTHING;
    SELECT id INTO selected FROM app.document_versions WHERE document_id=d.id AND content_hash=p_hash AND configuration=p_config;
    doc_status := CASE WHEN EXISTS (SELECT 1 FROM app.processors p
        JOIN app.collection_processor_approvals ca ON ca.processor_id=p.id AND ca.collection_id=d.collection_id
        JOIN app.collections c ON c.id=d.collection_id
        JOIN app.project_processor_approvals pa ON pa.processor_id=p.id AND pa.project_id=c.project_id
        WHERE p.enabled AND p.provider='gemini' AND p.roles @> '["embedding"]'::jsonb)
        THEN 'waiting_capacity' ELSE 'awaiting_approval' END;
    UPDATE app.documents SET active_version_id=selected,status=doc_status,media_type=j.media_type WHERE id=d.id;
    UPDATE app.ingestion_jobs SET status='completed',stage='snapshot_published',lease_token=NULL,lease_until=NULL,
        retryable=false,finished_at=clock_timestamp() WHERE id=j.id;
    RETURN jsonb_build_object('version_id',selected);
END $$
""",
"app.ingestion_authorized(uuid,uuid)": """
CREATE FUNCTION app.ingestion_authorized(p_job uuid,p_token uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.ingestion_jobs%ROWTYPE; d app.documents%ROWTYPE;
BEGIN
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job AND status='running' AND lease_token=p_token AND lease_until>clock_timestamp();
    IF NOT FOUND THEN RETURN false; END IF;
    PERFORM set_config('docweave.actor_id',j.actor_id::text,true),set_config('docweave.workspace_id',j.workspace_id::text,true);
    SELECT * INTO d FROM app.documents WHERE id=j.document_id;
    RETURN d.deleted_at IS NULL AND app.collection_can(d.collection_id,'write') AND (d.source_id IS NULL OR EXISTS (
        SELECT 1 FROM app.sources s JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
            WHERE s.id=d.source_id AND s.deleted_at IS NULL AND ds.active));
END $$
""",
"app.fail_ingestion(uuid,uuid,boolean)": """
CREATE FUNCTION app.fail_ingestion(p_job uuid,p_token uuid,p_transient boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE j app.ingestion_jobs%ROWTYPE;
BEGIN
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job;
    PERFORM 1 FROM app.workspaces WHERE id=j.workspace_id FOR UPDATE;
    SELECT * INTO j FROM app.ingestion_jobs WHERE id=p_job AND status='running' AND lease_token=p_token FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF NOT app.ingestion_authorized(p_job,p_token) THEN
        UPDATE app.ingestion_jobs SET status='blocked_policy',stage='authority_changed',lease_token=NULL,lease_until=NULL,finished_at=clock_timestamp() WHERE id=j.id;
        RETURN;
    END IF;
    UPDATE app.ingestion_jobs SET status=CASE WHEN p_transient AND attempts<3 THEN 'queued' ELSE 'failed' END,
        stage='preparation_failed',retryable=p_transient AND attempts<3,lease_token=NULL,lease_until=NULL,
        finished_at=CASE WHEN p_transient AND attempts<3 THEN NULL ELSE clock_timestamp() END WHERE id=j.id;
    UPDATE app.documents SET status=CASE WHEN active_version_id IS NULL THEN 'failed' ELSE 'stale' END WHERE id=j.document_id AND deleted_at IS NULL;
END $$
""",
"app.ingestion_artifacts()": """
CREATE FUNCTION app.ingestion_artifacts() RETURNS TABLE(id uuid) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT j.id FROM app.ingestion_jobs j JOIN app.documents d ON d.id=j.document_id WHERE d.deleted_at IS NULL
    UNION SELECT v.id FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id WHERE d.deleted_at IS NULL
$$
""",
"app.ingestion_recoverable(uuid)": """
CREATE FUNCTION app.ingestion_recoverable(p_job uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT status<>'running' OR lease_until<=clock_timestamp() FROM app.ingestion_jobs WHERE id=p_job
$$
""",
}


def downgrade():
    op.execute("DROP TRIGGER immutable_selection ON app.documentation_selections")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for table in reversed(TABLES):
        op.drop_table(table, schema="app")
    op.execute("""DO $$ DECLARE object record; BEGIN
        FOR object IN SELECT tablename FROM pg_tables WHERE schemaname='queue' LOOP
            EXECUTE format('DROP TABLE IF EXISTS queue.%I CASCADE',object.tablename);
        END LOOP;
        FOR object IN SELECT p.oid::regprocedure AS signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='queue' LOOP
            EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE',object.signature);
        END LOOP;
        FOR object IN SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='queue' AND t.typtype IN ('e','c') LOOP
            EXECUTE format('DROP TYPE IF EXISTS queue.%I CASCADE',object.typname);
        END LOOP;
    END $$""")
