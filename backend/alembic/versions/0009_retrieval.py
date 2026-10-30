"""Scoped native/BM25/vector corpus, with immutable generation and selection identity."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import VECTOR

revision = "0009_retrieval"
down_revision = "0008_ingestion"
branch_labels = None
depends_on = None


def record():
    return [sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,app,public")
    op.add_column("documentation_selections", sa.Column("approved_stack", JSONB()), schema="app")
    op.create_table("index_generations", *record(), sa.Column("model", sa.Text(), nullable=False), sa.Column("backend", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False), sa.Column("normalization", sa.Text(), nullable=False),
        sa.Column("chunker", sa.Text(), nullable=False), sa.Column("processor_ids", JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint("dimensions=768 AND normalization='unit-l2'", name=op.f("ck_index_generations_supported_vectors")),
        sa.CheckConstraint("jsonb_typeof(processor_ids)='array' AND jsonb_array_length(processor_ids)>0", name=op.f("ck_index_generations_processor_array")), schema="app")
    op.create_table("document_indexes", sa.Column("document_id", sa.UUID(), primary_key=True), sa.Column("generation_id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False), sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generation_id"], ["app.index_generations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_version_id"], ["app.document_versions.id"], ondelete="RESTRICT"), schema="app")
    op.create_table("chunks", *record(),
        *(sa.Column(name, sa.UUID(), nullable=False) for name in ("workspace_id", "project_id", "collection_id", "document_id", "document_version_id", "generation_id")),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in ("start_offset", "end_offset", "line_start", "line_end", "token_count")),
        sa.Column("heading", sa.Text()), sa.Column("content", sa.Text(), nullable=False), sa.Column("terms", JSONB(), nullable=False),
        sa.Column("search", TSVECTOR(), sa.Computed("to_tsvector('english'::regconfig,content)", persisted=True), nullable=False),
        sa.Column("embedding", VECTOR(768), nullable=False),
        sa.Column("source_url", sa.Text()), sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False), sa.Column("provenance", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id", "workspace_id"], ["app.collections.id", "app.collections.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id", "workspace_id"], ["app.projects.id", "app.projects.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id", "workspace_id"], ["app.documents.id", "app.documents.workspace_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_version_id"], ["app.document_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generation_id"], ["app.index_generations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("document_version_id", "generation_id", "start_offset", name="uq_chunks_span_generation"),
        sa.CheckConstraint("start_offset>=0 AND end_offset>start_offset AND char_length(content)=end_offset-start_offset", name=op.f("ck_chunks_exact_span")),
        sa.CheckConstraint("line_start>=1 AND line_end>=line_start AND token_count>=0", name=op.f("ck_chunks_valid_locator")),
        sa.CheckConstraint("public.vector_norm(embedding) BETWEEN 0.9999 AND 1.0001", name=op.f("ck_chunks_unit_embedding")), schema="app")
    op.create_index("ix_chunks_scope", "chunks", ["workspace_id", "project_id", "collection_id", "generation_id", "document_version_id"], schema="app")
    op.create_index("ix_chunks_search", "chunks", ["search"], schema="app", postgresql_using="gin")
    op.create_index("ix_chunks_embedding_hnsw", "chunks", ["embedding"], schema="app", postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_with={"m": 16, "ef_construction": 64})
    op.execute("ALTER TABLE app.chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.document_indexes ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON app.chunks,app.index_generations,app.document_indexes FROM PUBLIC,docweave_runtime,docweave_worker")
    op.execute("GRANT SELECT ON app.chunks,app.index_generations TO docweave_runtime")
    for statement in FUNCTIONS.values():
        op.execute(statement)
    op.execute("CREATE TRIGGER immutable_index_generation BEFORE UPDATE OR DELETE ON app.index_generations FOR EACH ROW EXECUTE FUNCTION app.immutable_index_generation()")
    op.execute("CREATE TRIGGER purge_document_chunks AFTER UPDATE OF deleted_at ON app.documents FOR EACH ROW EXECUTE FUNCTION app.purge_document_chunks()")
    op.execute("CREATE TRIGGER mark_prepared_stale BEFORE UPDATE OF active_version_id ON app.documents FOR EACH ROW EXECUTE FUNCTION app.mark_prepared_stale()")
    op.execute("CREATE POLICY runtime_read ON app.chunks FOR SELECT TO docweave_runtime USING (app.chunk_current(document_version_id,collection_id,generation_id))")
    for signature in FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature in ("app.immutable_index_generation()", "app.purge_document_chunks()", "app.mark_prepared_stale()"):
            continue
        role = "docweave_worker" if signature.startswith(("app.index_input(", "app.insert_chunks(", "app.activate_index(")) else "docweave_runtime"
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


FUNCTIONS = {
"app.immutable_index_generation()": """
CREATE FUNCTION app.immutable_index_generation() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
BEGIN
    IF TG_OP='DELETE' OR (to_jsonb(NEW)-'enabled') IS DISTINCT FROM (to_jsonb(OLD)-'enabled') THEN
        RAISE EXCEPTION 'Generation identity is immutable' USING ERRCODE='22023'; END IF;
    RETURN NEW;
END $$
""",
"app.index_policy(uuid,uuid,text)": """
CREATE FUNCTION app.index_policy(p_collection uuid,p_generation uuid,p_action text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT EXISTS (SELECT 1 FROM app.collections c JOIN app.index_generations g ON g.id=p_generation
        WHERE c.id=p_collection AND g.enabled AND app.collection_can(c.id,p_action)
        AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(g.processor_ids) wanted(id)
            LEFT JOIN app.processors p ON p.id=wanted.id
            WHERE p.id IS NULL OR NOT p.enabled OR p.provider<>'gemini' OR NOT p.roles @> '["embedding"]'::jsonb
                OR NOT EXISTS (SELECT 1 FROM app.project_processor_approvals a WHERE a.project_id=c.project_id AND a.processor_id=p.id)
                OR NOT EXISTS (SELECT 1 FROM app.collection_processor_approvals a WHERE a.collection_id=c.id AND a.processor_id=p.id)))
$$
""",
"app.index_source_current(uuid)": """
CREATE FUNCTION app.index_source_current(p_document uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT EXISTS (SELECT 1 FROM app.documents d JOIN app.collections c ON c.id=d.collection_id JOIN app.projects p ON p.id=c.project_id
        LEFT JOIN app.sources s ON s.id=d.source_id LEFT JOIN app.documentation_selections ds ON ds.id=s.source_selection_id
        WHERE d.id=p_document AND d.deleted_at IS NULL AND app.collection_can(c.id,'read') AND (d.source_id IS NULL OR
            (s.deleted_at IS NULL AND ds.active AND ds.project_id=p.id AND ds.workspace_id=p.workspace_id
                AND lower(ds.approved_stack->>'technology')=lower(ds.technology)
                AND EXISTS (SELECT 1 FROM jsonb_array_elements(p.stack) selected WHERE selected=ds.approved_stack))))
$$
""",
"app.chunk_current(uuid,uuid,uuid)": """
CREATE FUNCTION app.chunk_current(p_version uuid,p_collection uuid,p_generation uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT EXISTS (SELECT 1 FROM app.document_indexes i JOIN app.document_versions v ON v.id=i.document_version_id
        JOIN app.documents d ON d.id=i.document_id AND d.id=v.document_id
        WHERE v.id=p_version AND d.collection_id=p_collection AND i.generation_id=p_generation
            AND p_generation=nullif(current_setting('docweave.generation_id',true),'')::uuid
            AND app.index_source_current(d.id) AND app.index_policy(p_collection,p_generation,'read'))
$$
""",
"app.bm25_terms(text)": """
CREATE FUNCTION app.bm25_terms(p_content text) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
    SELECT coalesce(jsonb_object_agg(term,frequency),'{}'::jsonb) FROM (
        SELECT matched[1] AS term,count(*) AS frequency FROM regexp_matches(lower(p_content),'([a-z0-9_]+(?:[.:-][a-z0-9_]+)*)','g') matched
        GROUP BY matched[1]) counted
$$
""",
"app.index_input(uuid,uuid)": """
CREATE FUNCTION app.index_input(p_document uuid,p_generation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE d app.documents%ROWTYPE; v app.document_versions%ROWTYPE; g app.index_generations%ROWTYPE; existing integer;
BEGIN
    PERFORM set_config('docweave.generation_id',p_generation::text,true);
    PERFORM 1 FROM app.workspaces WHERE id=nullif(current_setting('docweave.workspace_id',true),'')::uuid FOR UPDATE;
    SELECT * INTO d FROM app.documents WHERE id=p_document AND deleted_at IS NULL;
    IF NOT FOUND OR NOT app.collection_can(d.collection_id,'read') THEN RAISE EXCEPTION 'Not found' USING ERRCODE='P0002'; END IF;
    IF NOT app.collection_can(d.collection_id,'write') THEN RAISE EXCEPTION 'Forbidden' USING ERRCODE='42501'; END IF;
    SELECT * INTO g FROM app.index_generations WHERE id=p_generation AND enabled FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Generation unavailable' USING ERRCODE='DW022'; END IF;
    IF NOT app.index_policy(d.collection_id,g.id,'write') THEN RAISE EXCEPTION 'Approval required' USING ERRCODE='DW020'; END IF;
    SELECT * INTO v FROM app.document_versions WHERE id=d.active_version_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Snapshot unavailable' USING ERRCODE='DW021'; END IF;
    IF NOT app.index_source_current(d.id) OR v.configuration IS DISTINCT FROM (g.chunker||':'||d.media_type) THEN
        RAISE EXCEPTION 'Snapshot unavailable' USING ERRCODE='DW021'; END IF;
    SELECT count(*) INTO existing FROM app.chunks WHERE document_version_id=v.id AND generation_id=g.id;
    RETURN jsonb_build_object('document_id',d.id,'version_id',v.id,'content_hash',v.content_hash,'configuration',v.configuration,
        'collection_id',d.collection_id,'existing_chunks',existing);
END $$
""",
"app.activate_index(uuid,uuid,uuid,integer)": """
CREATE FUNCTION app.activate_index(p_document uuid,p_generation uuid,p_version uuid,p_expected integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE snapshot jsonb; actual integer;
BEGIN
    snapshot := app.index_input(p_document,p_generation);
    IF (snapshot->>'version_id')::uuid IS DISTINCT FROM p_version THEN RAISE EXCEPTION 'Snapshot changed' USING ERRCODE='DW021'; END IF;
    SELECT count(*) INTO actual FROM app.chunks WHERE document_version_id=p_version AND generation_id=p_generation;
    IF p_expected IS NULL OR p_expected NOT BETWEEN 1 AND 10000 OR actual<>p_expected THEN
        RAISE EXCEPTION 'Incomplete index' USING ERRCODE='DW021'; END IF;
    INSERT INTO app.document_indexes(document_id,generation_id,workspace_id,document_version_id)
        SELECT id,p_generation,workspace_id,p_version FROM app.documents WHERE id=p_document
    ON CONFLICT(document_id,generation_id) DO UPDATE SET document_version_id=excluded.document_version_id;
    UPDATE app.documents SET status='ready' WHERE id=p_document;
END $$
""",
"app.insert_chunks(uuid,uuid,uuid,jsonb)": """
CREATE FUNCTION app.insert_chunks(p_document uuid,p_generation uuid,p_version uuid,p_chunks jsonb) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app,public AS $$
DECLARE snapshot jsonb; added integer;
BEGIN
    snapshot := app.index_input(p_document,p_generation);
    IF (snapshot->>'version_id')::uuid IS DISTINCT FROM p_version THEN RAISE EXCEPTION 'Snapshot changed' USING ERRCODE='DW021'; END IF;
    IF jsonb_typeof(p_chunks) IS DISTINCT FROM 'array' OR jsonb_array_length(p_chunks) NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'Invalid batch' USING ERRCODE='22023'; END IF;
    INSERT INTO app.chunks(workspace_id,project_id,collection_id,document_id,document_version_id,generation_id,start_offset,end_offset,
        heading,line_start,line_end,content,terms,token_count,embedding,source_url,captured_at,provenance)
    SELECT d.workspace_id,c.project_id,d.collection_id,d.id,p_version,p_generation,(item->>'start')::integer,(item->>'end')::integer,
        item->>'heading',(item->>'line_start')::integer,(item->>'line_end')::integer,item->>'content',tokens,
        (SELECT coalesce(sum(value::integer),0) FROM jsonb_each_text(tokens)),(item->>'embedding')::public.vector,v.source_url,v.created_at,
        jsonb_build_object('document_title',d.title,'source_id',s.id,'source_selection_id',ds.id,'docs_target',ds.docs_target,'coverage',ds.coverage,'approved_stack',ds.approved_stack)
    FROM jsonb_array_elements(p_chunks) item CROSS JOIN LATERAL (SELECT app.bm25_terms(item->>'content') tokens) t,
        app.documents d JOIN app.collections c ON c.id=d.collection_id JOIN app.document_versions v ON v.id=p_version
        LEFT JOIN app.sources s ON s.id=d.source_id LEFT JOIN app.documentation_selections ds ON ds.id=s.source_selection_id WHERE d.id=p_document
    ON CONFLICT(document_version_id,generation_id,start_offset) DO NOTHING;
    GET DIAGNOSTICS added=ROW_COUNT;
    RETURN added;
END $$
""",
"app.evaluation_versions(uuid,uuid,uuid[])": """
CREATE FUNCTION app.evaluation_versions(p_project uuid,p_generation uuid,p_collections uuid[])
RETURNS TABLE(version_id uuid,content_hash text,title text,source_url text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    SELECT DISTINCT v.id,v.content_hash,d.title,v.source_url FROM app.chunks c
        JOIN app.document_versions v ON v.id=c.document_version_id JOIN app.documents d ON d.id=v.document_id
    WHERE c.project_id=p_project AND c.generation_id=p_generation AND c.collection_id=ANY(p_collections)
        AND app.chunk_current(c.document_version_id,c.collection_id,c.generation_id)
$$
""",
"app.purge_document_chunks()": """
CREATE FUNCTION app.purge_document_chunks() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
BEGIN
    IF NEW.deleted_at IS NOT NULL THEN
        DELETE FROM app.chunks WHERE document_id=NEW.id;
        DELETE FROM app.document_indexes WHERE document_id=NEW.id;
    END IF;
    RETURN NEW;
END $$
""",
"app.mark_prepared_stale()": """
CREATE FUNCTION app.mark_prepared_stale() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
BEGIN
    IF NEW.deleted_at IS NULL AND NEW.active_version_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM app.document_indexes i WHERE i.document_id=NEW.id AND i.document_version_id<>NEW.active_version_id) THEN
        NEW.status := 'stale';
    END IF;
    RETURN NEW;
END $$
""",
}


def downgrade():
    op.execute("DROP POLICY runtime_read ON app.chunks")
    op.execute("DROP TRIGGER immutable_index_generation ON app.index_generations")
    op.execute("DROP TRIGGER purge_document_chunks ON app.documents")
    op.execute("DROP TRIGGER mark_prepared_stale ON app.documents")
    for signature in reversed(FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    op.drop_table("chunks", schema="app")
    op.drop_table("document_indexes", schema="app")
    op.drop_table("index_generations", schema="app")
    op.drop_column("documentation_selections", "approved_stack", schema="app")
