from sqlalchemy import text
import json

async def resume(connection,project,actor,profile,operation,body_hash,incoming,outgoing,key_hash):
    return await connection.scalar(text('SELECT app.personal_provider_resume(:project,:actor,:profile,:operation,:body,:incoming,:outgoing,:key)'),{'project':project,'actor':actor,'profile':profile,'operation':operation,'body':body_hash,'incoming':incoming,'outgoing':outgoing,'key':key_hash})

async def checkpoint(connection,identity,response):
    await connection.execute(text('SELECT app.personal_provider_checkpoint(:id,CAST(:response AS jsonb))'), {'id':identity,'response':json.dumps(response,allow_nan=False)})
async def claim(connection,project,actor,profile,operation,body_hash,incoming,outgoing):
    return await connection.scalar(text('SELECT app.personal_provider_claim(:project,:actor,:profile,:operation,:body,:incoming,:outgoing)'),{'project':project,'actor':actor,'profile':profile,'operation':operation,'body':body_hash,'incoming':incoming,'outgoing':outgoing})
async def settle(connection,identity,actual):
    await connection.execute(text('SELECT app.personal_provider_settle(:id,:actual)'),{'id':identity,'actual':actual})
