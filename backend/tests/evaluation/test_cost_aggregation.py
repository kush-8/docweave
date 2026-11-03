import copy
from datetime import date
from decimal import Decimal
import json
from uuid import uuid4

import pytest


def ledger(*rows):
    return {'scope': 'job_lifetime', 'invoice_verified': False, 'new_dispatch_inferred': False,
        'reservations': list(rows), 'retained_usd': sum((row['charged_usd'] for row in rows), Decimal(0)),
        'unsettled_usd': sum((row['charged_usd'] for row in rows if row['status'] != 'metered'), Decimal(0))}


def reservation(status='uncertain'):
    return {'id': uuid4(), 'profile_id': uuid4(), 'stage': 'generation', 'month': date(2026, 11, 1),
        'status': status, 'maximum_usd': Decimal('0.123456789012'),
        'actual_usd': Decimal('0.01') if status == 'metered' else None,
        'charged_usd': Decimal('0.01') if status == 'metered' else Decimal('0.123456789012'),
        'operation_hash': 'a'*64, 'body_hash': 'b'*64}


def test_aggregation_deduplicates_reservations_across_replay_and_json_roundtrip():
    from docweave.evaluation.costs import aggregate_job_costs
    uncertain, metered = reservation(), reservation('metered')
    first, second = ledger(uncertain), ledger(metered)
    saved = json.loads(json.dumps(first, default=str))
    result = aggregate_job_costs([first, second, saved])
    assert result['unique_reservations'] == 2
    assert result['retained_usd'] == Decimal('0.133456789012')
    assert result['unsettled_usd'] == Decimal('0.123456789012')
    assert result['conservative_usd'] == Decimal('0.246913578024')
    assert result['invoice_verified'] is False and result['new_dispatch_inferred'] is False
    assert result == aggregate_job_costs([saved, second, first])


def test_conflicting_snapshots_must_be_recaptured_not_silently_released():
    from docweave.evaluation.costs import aggregate_job_costs
    original = reservation()
    changed = {**original, 'status': 'metered', 'actual_usd': Decimal('0.01'), 'charged_usd': Decimal('0.01')}
    with pytest.raises(ValueError, match='Conflicting'):
        aggregate_job_costs([ledger(original), ledger(changed)])


@pytest.mark.parametrize('mutation', ['float', 'nan', 'negative', 'precision', 'charge', 'total', 'status', 'scope', 'invoice'])
def test_unusable_financial_evidence_is_rejected(mutation):
    from docweave.evaluation.costs import aggregate_job_costs
    value = ledger(reservation())
    row = value['reservations'][0]
    if mutation == 'float': row['maximum_usd'] = 0.1
    elif mutation == 'nan': row['maximum_usd'] = 'NaN'
    elif mutation == 'negative': row['charged_usd'] = '-0.01'
    elif mutation == 'precision': row['maximum_usd'] = '0.1234567890123'
    elif mutation == 'charge': row['charged_usd'] = '0'
    elif mutation == 'total': value['retained_usd'] = '0'
    elif mutation == 'status': row['status'] = 'settled'
    elif mutation == 'scope': value['scope'] = 'new_calls'
    else: value['invoice_verified'] = True
    with pytest.raises(ValueError): aggregate_job_costs([value])


def test_empty_verified_job_ledger_has_no_claims():
    from docweave.evaluation.costs import aggregate_job_costs
    result = aggregate_job_costs([ledger()])
    assert result['unique_reservations'] == 0 and result['retained_usd'] == 0
