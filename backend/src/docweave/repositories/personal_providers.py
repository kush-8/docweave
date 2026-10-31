from sqlalchemy import text
async def claim(connection,project,actor,profile,operation,body_hash,incoming,outgoing):
    return await connection.scalar(text('SELECT app.personal_provider_claim(:project,:actor,:profile,:operation,:body,:incoming,:outgoing)'),{'project':project,'actor':actor,'profile':profile,'operation':operation,'body':body_hash,'incoming':incoming,'outgoing':outgoing})
async def settle(connection,identity,actual):
    await connection.execute(text('SELECT app.personal_provider_settle(:id,:actual)'),{'id':identity,'actual':actual})
