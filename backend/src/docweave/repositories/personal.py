"""Direct-owner project RPCs. Workflow callers own transactions."""
import json
from sqlalchemy import text

async def project(connection, identity):
    return await connection.scalar(text('SELECT app.personal_project(:id)'), {'id':identity})

async def create_project(connection, body):
    return await connection.scalar(text('SELECT app.personal_create_project(CAST(:body AS jsonb))'), {'body':json.dumps(body)})

async def link_repository(connection, identity, body):
    return await connection.scalar(text('SELECT app.personal_link_repository(:id,CAST(:body AS jsonb))'), {'id':identity,'body':json.dumps(body)})

async def list_projects(connection, after, identity, limit):
    return list((await connection.execute(text('SELECT app.personal_list_projects(:after,:id,:limit)'), {'after':after,'id':identity,'limit':limit})).scalars())

async def catalog(connection, generation=None):
    return list((await connection.execute(text('SELECT app.catalog_entries(:generation)'), {'generation': generation})).scalars())


async def choose_documentation(connection, project, dependency, expected, revision, fallback, generation):
    return await connection.scalar(text('SELECT app.personal_choose_documentation(:project,:dependency,:expected,:revision,:fallback,:generation)'),
        {'project': project, 'dependency': dependency, 'expected': expected, 'revision': revision, 'fallback': fallback, 'generation': generation})


async def review_source(connection, project, dependency, expected, values):
    return await connection.scalar(text('SELECT app.personal_review_source(:project,:dependency,:expected,CAST(:values AS jsonb))'),
        {'project': project, 'dependency': dependency, 'expected': expected, 'values': json.dumps(values)})


async def private_source_entries(connection, project, generation):
    return list((await connection.execute(text('SELECT app.personal_private_source_entries(:project,:generation)'),
        {'project': project, 'generation': generation})).scalars())


async def conversation(connection, identity):
    return await connection.scalar(text('SELECT app.personal_conversation(:id)'), {'id':identity})

async def create_conversation(connection, project_id, profile_id):
    return await connection.scalar(text('SELECT app.personal_create_conversation(:project,:profile)'), {'project':project_id,'profile':profile_id})

async def retry_sync(connection, identity):
    return await connection.scalar(text('SELECT app.personal_retry_sync(:id)'), {'id':identity})

async def list_conversations(connection, project_id):
    return list((await connection.execute(text('SELECT app.personal_list_conversations(:id)'), {'id':project_id})).scalars())

async def turns(connection, identity):
    return list((await connection.execute(text('SELECT app.personal_list_turns(:id)'), {'id':identity})).scalars())

async def turn(connection, identity):
    return await connection.scalar(text('SELECT app.personal_turn(:id)'), {'id':identity})

async def append_turn(connection, conversation_id, key, message):
    return await connection.scalar(text('SELECT app.personal_append_turn(:id,:key,:message)'), {'id':conversation_id,'key':key,'message':message})

async def delete_conversation(connection, identity):
    return await connection.scalar(text('SELECT app.personal_delete_conversation(:id)'), {'id':identity})

async def claim_job(connection, identity):
    return await connection.scalar(text('SELECT app.personal_claim_job(:id)'), {'id':identity})

async def finish_job(connection, identity, token, result):
    return await connection.scalar(text('SELECT app.personal_finish_job(:id,:token,CAST(:result AS jsonb))'), {'id':identity,'token':token,'result':json.dumps(result)})

async def pending_jobs(connection):
    return list((await connection.execute(text('SELECT * FROM app.personal_pending_jobs()'))).mappings())

async def recover_jobs(connection):
    return await connection.scalar(text('SELECT app.personal_recover_jobs()'))

async def retry_stalled(connection, identity):
    await connection.execute(text('SET LOCAL search_path=queue,pg_catalog'))
    job = await connection.scalar(text("""SELECT j.id FROM queue.procrastinate_jobs j WHERE j.id=:id
        AND j.queue_name='personal' AND j.task_name IN ('docweave.personal','docweave.catalog','docweave.private_index') AND j.status='doing'
        AND (j.worker_id IS NULL OR EXISTS(SELECT 1 FROM queue.procrastinate_workers w
            WHERE w.id=j.worker_id AND w.last_heartbeat<now()-interval '30 seconds')) FOR UPDATE OF j"""), {'id':identity})
    if job is None:
        return False
    await connection.execute(text('SELECT queue.procrastinate_retry_job_v2(:id,now(),NULL,NULL,NULL)'), {'id':identity})
    return True

async def lock_project(connection, identity):
    await connection.execute(text('SELECT pg_advisory_lock(hashtextextended(:id,730004))'), {'id':str(identity)})

async def unlock_project(connection, identity):
    await connection.execute(text('SELECT pg_advisory_unlock(hashtextextended(:id,730004))'), {'id':str(identity)})


async def job_context(connection, identity, token):
    return await connection.scalar(text('SELECT app.personal_job_context(:id,:token)'),{'id':identity,'token':token})

async def catalog_state(connection, identity, token, generation):
    return list((await connection.execute(text('SELECT app.personal_catalog_state(:id,:token,:generation)'),{'id':identity,'token':token,'generation':generation})).scalars())

async def select_catalog(connection, identity, token, choices):
    return await connection.scalar(text('SELECT app.personal_select_catalog(:id,:token,CAST(:choices AS jsonb))'),{'id':identity,'token':token,'choices':json.dumps(choices)})


async def history(connection,job,token):
    return list((await connection.execute(text('SELECT app.personal_worker_history(:id,:token)'),{'id':job,'token':token})).scalars())

async def summary(connection,job,token,revision,value=None):
    return await connection.scalar(text('SELECT app.personal_worker_summary(:id,:token,:revision,CAST(:value AS jsonb))'),
        {'id':job,'token':token,'revision':revision,'value':json.dumps(value) if value is not None else None})

async def scopes(connection,job,token,generation):
    return list((await connection.execute(text('SELECT app.personal_worker_scopes(:id,:token,:generation)'),{'id':job,'token':token,'generation':generation})).scalars())
async def citation(connection,turn,identity):
    return await connection.scalar(text('SELECT app.personal_citation(:turn,:citation)'),{'turn':turn,'citation':identity})
async def profile(connection,identity):
    return await connection.scalar(text('SELECT app.personal_profile(:id)'),{'id':identity})

async def embedding_matches(connection,generation,profile):
    return await connection.scalar(text('SELECT app.personal_embedding_matches(:generation,:profile)'),{'generation':generation,'profile':profile})
async def processing_policy(connection,project):
    return await connection.scalar(text('SELECT app.personal_processing_policy(:project)'),{'project':project})
async def processors(connection):
    return list((await connection.execute(text('SELECT app.personal_required_processors()'))).scalars())
async def replace_processing_policy(connection,project,revision,processors):
    return await connection.scalar(text('SELECT app.personal_replace_processing_policy(:project,:revision,CAST(:processors AS jsonb))'),{'project':project,'revision':revision,'processors':json.dumps(processors)})

async def resource(connection,kind,identity):
    return await connection.scalar(text('SELECT app.personal_resource(:kind,:id)'),{'kind':kind,'id':identity})
async def review_document(connection,document,version,digest,rules):
    return await connection.scalar(text('SELECT app.personal_review_document(:document,:version,:hash,:rules)'),{'document':document,'version':version,'hash':digest,'rules':rules})

async def assessment(connection,document):
    return await connection.scalar(text('SELECT app.personal_assessment_view(:id)'),{'id':document})
