"""Narrow worker functions and operator-only lifecycle mutations."""
import json
from sqlalchemy import text
from docweave.core.guardrails import RULE_REVISION


async def fence(connection,epoch=None):
    return await connection.scalar(text('SELECT app.guardrail_fence(:revision,:epoch)'),{'revision':RULE_REVISION,'epoch':epoch})


async def reconcile(connection):
    return await connection.scalar(text('SELECT app.guardrail_reconcile(:revision)'),{'revision':RULE_REVISION})


async def claim(connection,job):
    return await connection.scalar(text('SELECT app.guardrail_claim(:job,:revision)'),{'job':job,'revision':RULE_REVISION})


async def finish(connection,job,token,assessment):
    return await connection.scalar(text('SELECT app.guardrail_finish(:job,:token,CAST(:assessment AS jsonb))'),
        {'job':job,'token':token,'assessment':json.dumps(assessment) if assessment is not None else None})


async def require_operator(connection):
    if await connection.scalar(text('SELECT current_user'))!='docweave_migrator':
        raise ValueError('Guardrail operations require the migration role')


async def activate(connection,expected_epoch):
    await require_operator(connection)
    return await connection.scalar(text('SELECT app.activate_guardrail_policy(:revision,:epoch)'),{'revision':RULE_REVISION,'epoch':expected_epoch})


async def retry(connection,version):
    await require_operator(connection)
    return await connection.scalar(text('SELECT app.guardrail_retry(:version)'),{'version':version})


async def review_catalog(connection,version,digest,epoch):
    await require_operator(connection)
    return await connection.scalar(text('SELECT app.review_guardrail_catalog(:version,:hash,:revision,:epoch)'),
        {'version':version,'hash':digest,'revision':RULE_REVISION,'epoch':epoch})


async def audit(connection,*,after=None,limit=100):
    await require_operator(connection)
    return list((await connection.execute(text('SELECT * FROM app.guardrail_events WHERE (CAST(:after AS uuid) IS NULL OR (created_at,id)>(SELECT created_at,id FROM app.guardrail_events WHERE id=CAST(:after AS uuid))) ORDER BY created_at,id LIMIT :limit'),
        {'after':after,'limit':min(max(limit,1),100)})).mappings())


async def status(connection):
    await require_operator(connection)
    policy=dict((await connection.execute(text('SELECT rule_revision,epoch FROM app.guardrail_policy WHERE id=1'))).mappings().one())
    policy['rescans']=[dict(row) for row in (await connection.execute(text('SELECT status,count(*) AS count FROM app.guardrail_rescans WHERE epoch=:epoch GROUP BY status ORDER BY status'),{'epoch':policy['epoch']})).mappings()]
    return policy


async def review_snapshot(connection,version):
    await require_operator(connection)
    row=(await connection.execute(text('''SELECT a.*,app.guardrail_document_state(v.id) AS rescan_status
        FROM app.document_versions v JOIN app.documents d ON d.id=v.document_id
        JOIN app.collections c ON c.id=d.collection_id JOIN app.public_catalog_revisions r ON r.id=c.catalog_revision_id
        JOIN app.document_assessments a ON a.document_version_id=v.id
        WHERE v.id=:version AND d.deleted_at IS NULL AND r.enabled AND r.source_approved'''),{'version':version})).mappings().first()
    if row is None:
        raise ValueError('Public review snapshot unavailable')
    return dict(row)
