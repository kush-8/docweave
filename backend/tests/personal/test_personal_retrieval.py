"""Public documentation may be shared; private chunks and revoked versions may not."""
import hashlib
from uuid import UUID,uuid4
import pytest
from sqlalchemy import text
from tests.database.test_database import A,B,PA,PB,WA,databases,test_urls
from docweave.core.identity import Actor
from docweave.rag.retrieval import retrieve_channels

pytestmark=pytest.mark.anyio

async def seed(owner, *, model="fixture", backend="fixture", processor_ids=None, coverage=None):
    vector=[1.0]+[0.0]*767
    async with owner.begin() as c:
        await c.execute(text("UPDATE app.projects SET owner_user_id=CASE WHEN id=:pa THEN CAST(:a AS uuid) ELSE CAST(:b AS uuid) END WHERE id IN (:pa,:pb)"),{'pa':PA,'pb':PB,'a':A,'b':B})
        generation=await c.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES (:model,:backend,768,'unit-l2','fixture',CAST(:processors AS jsonb),true) RETURNING id"),{'model':model,'backend':backend,'processors':__import__('json').dumps(processor_ids or ['fixture'])})
        revision=await c.scalar(text("""INSERT INTO app.public_catalog_revisions(technology,ecosystem,docs_target,coverage,origin,path_prefix,source_url,attribution,source_hash,enabled,source_approved) VALUES('react','javascript','19',CAST(:coverage AS jsonb),'https://react.dev','/','https://react.dev/reference','React',:hash,true,true) RETURNING id"""),{'hash':'a'*64,'coverage':__import__('json').dumps(coverage or {'granularity':'exact','version':'19'})})
        collection=await c.scalar(text("INSERT INTO app.collections(catalog_revision_id,name) VALUES(:r,'Public') RETURNING id"),{'r':revision})
        selection=await c.scalar(text("""INSERT INTO app.documentation_selections(catalog_revision_id,approved_by,technology,docs_target,coverage,origin,path_prefix,source_url,attribution) SELECT id,:a,technology,docs_target,coverage,origin,path_prefix,source_url,attribution FROM app.public_catalog_revisions WHERE id=:r RETURNING id"""),{'a':A,'r':revision})
        source=await c.scalar(text('INSERT INTO app.sources(collection_id,source_selection_id) VALUES(:c,:s) RETURNING id'),{'c':collection,'s':selection})
        document=await c.scalar(text("INSERT INTO app.documents(collection_id,source_id,title,media_type) VALUES(:c,:s,'Public React','text/plain') RETURNING id"),{'c':collection,'s':source})
        content='React state uses hooks.'
        digest=hashlib.sha256(content.encode()).hexdigest()
        version=await c.scalar(text("INSERT INTO app.document_versions(document_id,content_hash,configuration,source_url) VALUES(:d,:hash,'fixture:text/plain','https://react.dev/reference') RETURNING id"),{'d':document,'hash':digest})
        await c.execute(text("UPDATE app.documents SET active_version_id=:v,status='ready' WHERE id=:d"),{'v':version,'d':document})
        await c.execute(text("INSERT INTO app.document_indexes(document_id,generation_id,document_version_id) VALUES(:d,:g,:v)"),{'d':document,'g':generation,'v':version})
        chunk=await c.scalar(text("""INSERT INTO app.chunks(collection_id,document_id,document_version_id,generation_id,start_offset,end_offset,line_start,line_end,content,terms,token_count,embedding,captured_at,provenance) VALUES(:c,:d,:v,:g,0,:end,1,1,:content,app.bm25_terms(:content),4,CAST(:vector AS public.vector),now(),'{}') RETURNING id"""),{'c':collection,'d':document,'v':version,'g':generation,'end':len(content),'content':content,'vector':str(vector)})
        await c.execute(text("INSERT INTO app.document_assessments(document_version_id,content_hash,parser_config_hash,rule_revision,credential_blocked,injection_flagged,complete) VALUES(:v,:hash,:config,'deterministic-v1',false,false,true)"),{'v':version,'hash':digest,'config':'b'*64})
        for project in (PA,PB):
            await c.execute(text('UPDATE app.projects SET stack=CAST(:stack AS jsonb) WHERE id=:p'),{'stack':'[{"id":"react","technology":"react","ecosystem":"javascript","docs_target":"19"}]','p':project})
            await c.execute(text("INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id) VALUES(:p,'react',:r)"),{'p':project,'r':revision})
    return generation,revision,collection,version,chunk,vector

async def test_shared_public_retrieval_is_selected_scoped_and_revocation_safe(databases):
    owner,runtime=databases
    generation,revision,collection,version,chunk,vector=await seed(owner)
    for actor,project in ((A,PA),(B,PB)):
        result=await retrieve_channels(Actor(actor),project,'React state',collection_ids=[collection],generation_id=generation,query_vector=vector,engine=runtime,lexical='bm25')
        assert result['lexical'][0]['chunk_id']==chunk
        assert result['vector'][0]['chunk_id']==chunk
    async with owner.begin() as c:
        await c.execute(text('DELETE FROM app.project_catalog_selections WHERE project_id=:p'),{'p':PA})
    from docweave.rag.contracts import RetrievalError
    with pytest.raises(RetrievalError):
        await retrieve_channels(Actor(A),PA,'React',collection_ids=[collection],generation_id=generation,query_vector=vector,engine=runtime)
    result=await retrieve_channels(Actor(B),PB,'React',collection_ids=[collection],generation_id=generation,query_vector=vector,engine=runtime)
    assert result['eligible_count']==1
    async with owner.begin() as c:
        await c.execute(text("UPDATE app.document_assessments SET credential_blocked=true WHERE document_version_id=:v"),{'v':version})
    result=await retrieve_channels(Actor(B),PB,'React',collection_ids=[collection],generation_id=generation,query_vector=vector,engine=runtime)
    assert result['eligible_count']==0 and not result['vector']
