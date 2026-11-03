"""Evaluation turns through the ordinary HTTP authority and durable-job boundaries."""
import time
import hashlib
from uuid import UUID, uuid5


async def execute_http_turn(case, *, client, headers, conversation_id, execute_job):
    conversation_id = UUID(str(conversation_id))
    result = {'case_id': case.id, 'query_sha256': hashlib.sha256(case.query.encode()).hexdigest(), 'semantic_quality_evidence': False}
    started = time.perf_counter()
    response = await client.post(f'/api/v1/conversations/{conversation_id}/turns',
        json={'message': case.query, 'idempotency_key': str(uuid5(conversation_id, case.id))}, headers=headers)
    result['append_http_status'] = response.status_code
    if response.status_code != 202:
        result.update(http_status=response.status_code,
            outcome='http_denied' if response.status_code in (401, 403, 404) else 'http_error')
    else:
        turn = response.json()
        turn_id = UUID(turn['id'])
        result['turn_id'] = str(turn_id)
        pipeline = None
        if turn['status'] in ('queued', 'waiting_for_sources'):
            try:
                pipeline = await execute_job(str(turn_id))
            except Exception as error:
                result['execution_error'] = type(error).__name__
        response = await client.get(f'/api/v1/turns/{turn_id}')
        result['http_status'] = response.status_code
        if response.status_code == 200:
            released = response.json()
            result.update(outcome='execution_error' if 'execution_error' in result else 'turn_result', released_turn=released)
        else:
            result['outcome'] = 'http_denied' if response.status_code in (401, 403, 404) else 'http_error'
        if pipeline is not None:
            result['pipeline'] = pipeline if response.status_code == 200 and result['released_turn']['status'] == 'completed' else {
                key: pipeline[key] for key in ('implementation', 'stages', 'end_to_end_ms', 'retrieval_configuration', 'ledger') if key in pipeline}
    result['end_to_end_ms'] = (time.perf_counter() - started) * 1000
    return result
