"""Private evaluation capture around the ordinary admitted answer engine."""
import copy
import hashlib
import json
import time
from uuid import UUID

from docweave.db.sessions import domain_session
from docweave.core.paths import ROOT
from docweave.evaluation.fingerprint import source_fingerprint
from docweave.integrations.answers import answer_result
from docweave.repositories import personal as repository
from docweave.services.answer_engine import AnswerEngine
from docweave.services.guardrails import current_policy, release_turn
from docweave.services.personal_worker import run_personal_job


class EvaluationAnswerEngine(AnswerEngine):
    def __init__(self, job, *, capture, **kwargs):
        super().__init__(job, **kwargs)
        self.capture = capture
        capture.update(job_id=job['id'], generation_id=str(self.generation_id),
            context_revision=job['project']['context_revision'], semantic_quality_evidence=False,
            actor_id=job['actor_id'], turn_id=job['turn']['id'],
            answer_kind=None, retrieved_top_10=[], stages=[])

    async def profile(self, identity, role):
        if role == 'reranking':
            self.capture['retrieved_top_10'] = copy.deepcopy(self.hits[:10])
        return await super().profile(identity, role)

    async def dispatch(self, payload, profile, stage, embedding=False):
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        timing = {'stage': stage, 'profile_id': profile['id'], 'model': profile['model'],
                  'request_sha256': hashlib.sha256(body).hexdigest()}
        self.capture['stages'].append(timing)
        started = time.perf_counter()
        try:
            response = await super().dispatch(payload, profile, stage, embedding)
            timing['completed'] = True
            usage = response.get('usage', response.get('usageMetadata', {}))
            usage = usage if isinstance(usage, dict) else {}
            timing['reported_usage'] = {key: usage[key] for key in
                ('prompt_tokens', 'completion_tokens', 'total_tokens', 'promptTokenCount', 'totalTokenCount')
                if type(usage.get(key)) is int and usage[key] >= 0}
            details = usage.get('completion_tokens_details', {})
            if isinstance(details, dict) and type(details.get('reasoning_tokens')) is int and details['reasoning_tokens'] >= 0:
                timing['reported_usage']['reasoning_tokens'] = details['reasoning_tokens']
            if stage == 'generation':
                evidence = json.loads(payload['messages'][1]['content'])['evidence']
                result = answer_result(response, evidence, profile['model'])
                self.capture.update(answer_kind=result['kind'], blocks=result['blocks'])
            return response
        finally:
            timing['latency_ms'] = (time.perf_counter() - started) * 1000

    async def answer(self, turn, project, required):
        result = await super().answer(turn, project, required)
        self.capture['answer'] = copy.deepcopy(result)
        self.capture['policy_epoch'] = self.guardrail_epoch
        return result


async def capture_personal_job(job_id, *, engine, read_engine, settings, client, config, generation_id):
    capture = {'job_id': str(job_id), 'semantic_quality_evidence': False}
    capture['implementation'] = source_fingerprint(paths=[
        *(ROOT / 'backend/src/docweave').rglob('*.py'),
        *(ROOT / 'backend/alembic/versions').glob('*.py'), ROOT / 'backend/uv.lock'])
    capture['retrieval_configuration'] = {'lexical': config.get('RAG_LEXICAL_STRATEGY', 'bm25'),
        'vector': config.get('RAG_VECTOR_STRATEGY', 'exact')}
    def factory(job, authorize):
        return EvaluationAnswerEngine(job, capture=capture, engine=engine, read_engine=read_engine,
            config=config, generation_id=generation_id, authorize=authorize)
    started = time.perf_counter()
    await run_personal_job(job_id, engine=engine, settings=settings, client=client,
        generation_id=generation_id, answerer_factory=factory)
    capture['end_to_end_ms'] = (time.perf_counter() - started) * 1000
    if 'turn_id' in capture:
        async with engine.begin() as connection:
            await current_policy(connection, capture.get('policy_epoch'))
        async with domain_session(read_engine, UUID(capture['actor_id'])) as connection:
            turn = await repository.turn(connection, UUID(capture['turn_id']))
        capture['released_turn'] = release_turn(turn) if turn else None
        if not turn or capture['released_turn']['status'] != 'completed':
            for key in ('answer', 'blocks'):
                capture.pop(key, None)
            capture.update(answer_kind=None, retrieved_top_10=[])
    return capture
