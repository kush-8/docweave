"""Operator-only job-lifetime claims; reported usage is not fresh spending."""
from decimal import Decimal, InvalidOperation
from datetime import date
import re
from uuid import UUID
from sqlalchemy import text


def _money(value):
    if type(value) not in (str, int, Decimal):
        raise ValueError('Evaluation money must use exact decimal values')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError('Invalid evaluation amount')
        rounded = amount.quantize(Decimal('0.000000000001'))
        if rounded != amount:
            raise ValueError('Evaluation amount exceeds ledger precision')
        return rounded
    except InvalidOperation:
        raise ValueError('Invalid evaluation amount') from None


def aggregate_job_costs(ledgers):
    """Deduplicate exact job-lifetime snapshots; conflicting observations need a fresh read."""
    unique = {}
    fields = ('id', 'profile_id', 'stage', 'month', 'status', 'maximum_usd', 'actual_usd', 'charged_usd', 'operation_hash', 'body_hash')
    for ledger in ledgers:
        if (not isinstance(ledger, dict) or ledger.get('scope') != 'job_lifetime'
            or ledger.get('invoice_verified') is not False or ledger.get('new_dispatch_inferred') is not False
            or not isinstance(ledger.get('reservations'), list)):
            raise ValueError('Job-lifetime ledger evidence is required')
        retained, unsettled, seen = Decimal(0), Decimal(0), set()
        for source in ledger['reservations']:
            if not isinstance(source, dict) or set(source) != set(fields):
                raise ValueError('Invalid evaluation reservation')
            row = {key: source[key] for key in fields}
            row['id'], row['profile_id'] = str(UUID(str(row['id']))), str(UUID(str(row['profile_id'])))
            month = date.fromisoformat(str(row['month']))
            if month.day != 1 or row['stage'] not in ('summarization', 'query_resolution', 'query_embedding', 'reranking', 'generation'):
                raise ValueError('Invalid evaluation attribution')
            row['month'] = month.isoformat()
            if any(not isinstance(row[key], str) or not re.fullmatch('[0-9a-f]{64}', row[key]) for key in ('operation_hash', 'body_hash')):
                raise ValueError('Invalid evaluation operation identity')
            for key in ('maximum_usd', 'charged_usd', 'actual_usd'):
                row[key] = None if key == 'actual_usd' and row[key] is None else _money(row[key])
            if row['status'] not in ('reserved', 'uncertain', 'metered') or (row['status'] == 'reserved' and row['actual_usd'] is not None) or (row['status'] == 'metered' and row['actual_usd'] is None):
                raise ValueError('Invalid evaluation reservation status')
            if row['maximum_usd'] > Decimal('1000000000000') or (row['actual_usd'] is not None and row['actual_usd'] > Decimal('1000000000000')):
                raise ValueError('Evaluation amount exceeds ledger bounds')
            charge = row['actual_usd'] if row['status'] == 'metered' else max(row['maximum_usd'], row['actual_usd'] or Decimal(0))
            if row['charged_usd'] != charge or row['id'] in seen:
                raise ValueError('Invalid or duplicated evaluation charge')
            seen.add(row['id'])
            retained += charge
            unsettled += charge if row['status'] != 'metered' else Decimal(0)
            if row['id'] in unique and unique[row['id']] != row:
                raise ValueError('Conflicting reservation snapshots; recapture the current ledger')
            unique[row['id']] = row
        if retained != _money(ledger.get('retained_usd')) or unsettled != _money(ledger.get('unsettled_usd')):
            raise ValueError('Evaluation ledger totals differ from its reservations')
    rows = [unique[identity] for identity in sorted(unique)]
    return {'scope': 'captured_job_lifetimes', 'invoice_verified': False, 'new_dispatch_inferred': False,
        'unique_reservations': len(rows), 'reservations': rows,
        'retained_usd': sum((row['charged_usd'] for row in rows), Decimal(0)),
        'unsettled_usd': sum((row['charged_usd'] for row in rows if row['status'] != 'metered'), Decimal(0)),
        'conservative_usd': sum((max(row['maximum_usd'], row['charged_usd']) for row in rows), Decimal(0))}


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
