"""Operator-only job-lifetime claims; reported usage is not fresh spending."""
from decimal import Decimal
from uuid import UUID
from sqlalchemy import text


async def capture_job_costs(job_id, *, engine):
    async with engine.begin() as connection:
        await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        if await connection.scalar(text('SELECT current_user')) != 'docweave_migrator':
            raise ValueError('Evaluation accounting requires the migration role')
        identity = UUID(str(job_id))
        if not await connection.scalar(text('SELECT EXISTS(SELECT 1 FROM app.personal_jobs WHERE id=:id)'), {'id': identity}):
            raise ValueError('Unknown evaluation job')
        # shortcut: current five admitted stages; extend attribution when adding a new AnswerEngine stage.
        rows = list((await connection.execute(text("""SELECT DISTINCT r.id,r.profile_id,stage.name AS stage,
            r.month,r.status,r.maximum_usd,r.actual_usd,r.charged_usd,c.operation_hash,c.body_hash
            FROM app.personal_jobs j JOIN app.conversations chat ON chat.id=j.conversation_id
            JOIN app.cost_reservations r ON r.actor_id=j.actor_id AND r.project_id=chat.project_id
            JOIN app.personal_provider_calls c ON c.reservation_id=r.id
            CROSS JOIN (VALUES ('summarization'),('query_resolution'),('query_embedding'),('reranking'),('generation')) stage(name)
            WHERE j.id=:id AND c.key_hash=encode(sha256(convert_to(j.id::text||':'||stage.name,'UTF8')),'hex')
            ORDER BY stage.name,r.id"""), {'id': identity})).mappings())
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Ambiguous evaluation reservation attribution')
    return {'scope': 'job_lifetime', 'invoice_verified': False, 'new_dispatch_inferred': False,
        'reservations': [dict(row) for row in rows],
        'retained_usd': sum((row['charged_usd'] for row in rows), Decimal(0)),
        'unsettled_usd': sum((row['charged_usd'] for row in rows if row['status'] != 'metered'), Decimal(0))}
