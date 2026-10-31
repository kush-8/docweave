"""Shared catalog worker SQL; no direct table grants to workers."""
import json
from sqlalchemy import text
from docweave.repositories.rag.vector import vector_literal

async def definitions(connection):
    return list((await connection.execute(text('SELECT app.personal_catalog_definitions()'))).scalars())
async def reconcile(connection,project,actor,choices,generation):
    return await connection.scalar(text('SELECT app.personal_reconcile_catalog(:project,:actor,CAST(:choices AS jsonb),:generation)'),{'project':project,'actor':actor,'choices':json.dumps(choices),'generation':generation})
async def claim(connection,identity):
    return await connection.scalar(text('SELECT app.claim_catalog_job(:id)'),{'id':identity})
async def authorized(connection,identity,token):
    return await connection.scalar(text('SELECT app.catalog_job_authorized(:id,:token)'),{'id':identity,'token':token})
async def snapshot(connection,identity,token):
    return await connection.scalar(text('SELECT app.catalog_snapshot(:id,:token)'),{'id':identity,'token':token})
async def publish_snapshot(connection,identity,token,version,parsed,assessment):
    return await connection.scalar(text('SELECT app.publish_catalog_snapshot(:id,:token,:version,CAST(:parsed AS jsonb),CAST(:assessment AS jsonb))'),{'id':identity,'token':token,'version':version,'parsed':json.dumps({key:parsed[key] for key in ('sha256','configuration')}),'assessment':json.dumps(assessment)})
async def index_input(connection,identity,token):
    return await connection.scalar(text('SELECT app.catalog_index_input(:id,:token)'),{'id':identity,'token':token})
async def publish_index(connection,identity,token,rows,expected):
    for start in range(0,len(rows),64):
        await connection.execute(text('SELECT app.catalog_insert_chunks(:id,:token,CAST(:chunks AS jsonb))'),{'id':identity,'token':token,'chunks':json.dumps([{**row,'embedding':vector_literal(row['embedding'])} for row in rows[start:start+64]])})
    return await connection.scalar(text('SELECT app.catalog_activate_index(:id,:token,:expected)'),{'id':identity,'token':token,'expected':expected})
async def finish(connection,identity,token,status):
    return await connection.scalar(text('SELECT app.finish_catalog_job(:id,:token,:status)'),{'id':identity,'token':token,'status':status})
async def wake_waits(connection):
    return await connection.scalar(text('SELECT app.wake_personal_waits()'))

async def embedding_authorized(connection,job,token,profile):
    return await connection.scalar(text('SELECT app.catalog_embedding_authorized(:job,:token,:profile)'),{'job':job,'token':token,'profile':profile})
