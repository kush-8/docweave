"""Offline capture inventory, frozen configuration and conservative ledger aggregation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from docweave.evaluation.costs import aggregate_job_costs
from docweave.evaluation.frozen import load_frozen_sources, read_bounded


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False).encode()).hexdigest()


def summarize_offline_workload(dataset, folder, batch):
    parsed = load_frozen_sources(dataset, folder)
    if set(parsed) != {url for case in dataset.cases for url in case.sources}:
        raise ValueError('Complete frozen sources are required')
    manifest_hash = hashlib.sha256(read_bounded(Path(folder)/'manifest.json', 1024*1024)).hexdigest()
    if (not isinstance(batch, dict) or batch.get('dataset_sha256') != dataset._sha256
        or batch.get('sources_manifest_sha256') != manifest_hash or not isinstance(batch.get('cases'), dict)
        or set(batch['cases']) != {case.id for case in dataset.cases}):
        raise ValueError('Complete dataset-bound captures are required')
    configuration = batch.get('configuration')
    required = {'generation_id', 'implementation_sha256', 'fixture_sha256', 'transport', 'guardrail_epoch', 'retrieval_configuration', 'profiles'}
    if not isinstance(configuration, dict) or set(configuration) != required or configuration['transport'] != 'intercepted':
        raise ValueError('Only explicit secret-free offline configuration is supported')
    generation = str(UUID(str(configuration['generation_id'])))
    for key in ('implementation_sha256', 'fixture_sha256'):
        if not isinstance(configuration[key], str) or not re.fullmatch('[0-9a-f]{64}', configuration[key]):
            raise ValueError('Invalid frozen implementation identity')
    if type(configuration['guardrail_epoch']) is not int or configuration['guardrail_epoch'] < 1:
        raise ValueError('Invalid guardrail epoch')
    retrieval = configuration['retrieval_configuration']
    if (not isinstance(retrieval, dict) or set(retrieval) != {'lexical', 'vector'}
        or retrieval['lexical'] not in ('native', 'bm25') or retrieval['vector'] not in ('exact', 'hnsw')):
        raise ValueError('Invalid retrieval configuration')
    profiles = configuration['profiles']
    roles = {'embedding', 'query_resolution', 'reranking', 'generation'}
    if not isinstance(profiles, dict) or not roles <= set(profiles) <= roles | {'summarization'}:
        raise ValueError('Required profiles must be frozen')
    for profile in profiles.values():
        if not isinstance(profile, dict) or set(profile) != {'id', 'model'} or not isinstance(profile['model'], str) or not profile['model'].strip():
            raise ValueError('Invalid frozen profile')
        UUID(str(profile['id']))
    blocked = batch.get('source_blocked_answer_cases')
    answerable = {case.id for case in dataset.cases if case.kind == 'answerable'}
    if not isinstance(blocked, list) or any(not isinstance(identity, str) for identity in blocked) or len(set(blocked)) != len(blocked) or not set(blocked) <= answerable:
        raise ValueError('Invalid declared source blockers')
    outcomes, statuses, turns, ledgers = Counter(), Counter(), set(), []
    captured = 0
    for case in dataset.cases:
        final = batch['cases'][case.id]
        if not isinstance(final, dict) or not isinstance(final.get('history'), list) or len(final['history']) != len(case.history):
            raise ValueError('Every declared history turn must be captured')
        records = [*final['history'], final]
        for index, (query, record) in enumerate(zip([*case.history, case.query], records, strict=True)):
            identity = case.id if index == len(case.history) else case.id+':history:'+str(index)
            if (not isinstance(record, dict) or record.get('case_id') != identity
                or record.get('query_sha256') != hashlib.sha256(query.encode()).hexdigest()
                or record.get('semantic_quality_evidence', False) is not False):
                raise ValueError('Capture question identity differs')
            append, status = record.get('append_http_status'), record.get('http_status')
            if any(type(code) is not int or not 100 <= code <= 599 for code in (append, status)):
                raise ValueError('Invalid HTTP capture status')
            outcome = record.get('outcome')
            if outcome not in ('turn_result', 'http_denied', 'http_error', 'execution_error'):
                raise ValueError('Invalid execution outcome')
            outcomes[outcome] += 1
            captured += 1
            pipeline = record.get('pipeline')
            if append != 202:
                if outcome not in ('http_denied', 'http_error') or pipeline is not None or record.get('ledger') is not None:
                    raise ValueError('Rejected submission cannot claim execution evidence')
                continue
            turn = str(UUID(str(record.get('turn_id'))))
            if turn in turns:
                raise ValueError('One admitted turn cannot represent multiple questions')
            turns.add(turn)
            released = record.get('released_turn')
            if released is not None:
                if (not isinstance(released, dict) or status != 200 or str(UUID(str(released.get('id')))) != turn
                    or released.get('message') not in (query, '') or not isinstance(released.get('status'), str)):
                    raise ValueError('Released turn identity differs')
                statuses[released['status']] += 1
            evidence = []
            if record.get('ledger') is not None:
                evidence.append(record['ledger'])
            if pipeline is not None:
                if not isinstance(pipeline, dict) or pipeline.get('implementation', {}).get('sha256') != configuration['implementation_sha256']:
                    raise ValueError('Captured implementation differs')
                if 'generation_id' in pipeline and str(pipeline['generation_id']) != generation:
                    raise ValueError('Captured index generation differs')
                if 'policy_epoch' in pipeline and pipeline['policy_epoch'] != configuration['guardrail_epoch']:
                    raise ValueError('Captured guardrail epoch differs')
                if pipeline.get('retrieval_configuration') != retrieval:
                    raise ValueError('Captured retrieval configuration differs')
                if not isinstance(pipeline.get('stages'), list):
                    raise ValueError('Invalid captured stages')
                for stage in pipeline['stages']:
                    if not isinstance(stage, dict):
                        raise ValueError('Invalid captured stage')
                    role = 'embedding' if stage.get('stage') == 'query_embedding' else stage.get('stage')
                    expected = profiles.get(role)
                    if not expected or str(stage.get('profile_id')) != str(expected['id']) or stage.get('model') != expected['model']:
                        raise ValueError('Captured profile differs from frozen configuration')
                if pipeline.get('ledger') is not None:
                    evidence.append(pipeline['ledger'])
            if not evidence:
                raise ValueError('Every admitted execution requires ledger evidence, including errors')
            ledgers.extend(evidence)
    costs = aggregate_job_costs(ledgers)
    for row in costs['reservations']:
        role = 'embedding' if row['stage'] == 'query_embedding' else row['stage']
        if role not in profiles or row['profile_id'] != str(profiles[role]['id']):
            raise ValueError('Ledger profile differs from frozen configuration')
    return {'mode': 'offline_intercepted_transport', 'dataset_sha256': dataset._sha256,
        'sources_manifest_sha256': manifest_hash, 'configuration_sha256': _digest(configuration),
        'captures_sha256': _digest(batch), 'planned_turns': sum(len(case.history)+1 for case in dataset.cases),
        'captured_turns': captured, 'accepted_turns': len(turns), 'outcomes': dict(outcomes),
        'released_statuses': dict(statuses), 'source_blocked_answer_cases': sorted(blocked), 'costs': costs,
        'release_ready': False, 'semantic_quality_evidence': False}
