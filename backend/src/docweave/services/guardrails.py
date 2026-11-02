"""Rescan immutable local artifacts; never fetch, embed or replay provider calls."""
from dataclasses import asdict
import hashlib
import json
from uuid import UUID
from sqlalchemy.exc import DBAPIError
from docweave.core.guardrails import assess_text
from docweave.rag.contracts import HostedError
from docweave.repositories import guardrails as repository


async def current_policy(connection,epoch=None):
    try:
        return await repository.fence(connection,epoch)
    except DBAPIError:
        raise HostedError('guardrail_changed') from None


def review_page(store,snapshot,offset=0):
    if type(offset) is not int or not 0<=offset<=2_000_000:
        raise ValueError('Invalid review offset')
    parsed=json.loads(store.read(snapshot['document_version_id']))
    if not isinstance(parsed,dict) or not isinstance(parsed.get('text'),str) or not isinstance(parsed.get('configuration'),str):
        raise ValueError('Invalid review artifact')
    assessment=assess_text(parsed['text'],parser_config={'configuration':parsed['configuration']})
    if assessment.content_hash!=snapshot['content_hash'] or assessment.parser_config_hash!=snapshot['parser_config_hash']:
        raise ValueError('Review artifact changed')
    return {**snapshot,'text':parsed['text'][offset:offset+16000],
        'next_offset':offset+16000 if len(parsed['text'])>offset+16000 else None}


def release_turn(turn):
    if turn and turn.get('status')=='completed':
        for field in ('message','answer'):
            assessment=assess_text(turn.get(field) or '')
            if not assessment.complete or assessment.credential_blocked or assessment.injection_flagged:
                return {**turn,'status':'blocked_policy','message':'','answer':None,'citations':[],
                    'progress':'Historical context is held by the current guardrail rules.'}
    return turn


async def reconcile_rescans(engine):
    async with engine.begin() as connection:
        return await repository.reconcile(connection)


async def run_rescan(job_id,*,engine,store):
    async with engine.begin() as connection:
        job=await repository.claim(connection,job_id)
    if job is None:
        return
    assessment=None
    try:
        parsed=json.loads(store.read(job['document_version_id']))
        if (not isinstance(parsed,dict) or not isinstance(parsed.get('text'),str)
            or parsed.get('configuration')!=job['configuration']
            or hashlib.sha256(parsed['text'].encode()).hexdigest()!=job['content_hash']):
            raise ValueError('Snapshot mismatch')
        assessment=asdict(assess_text(parsed['text'],document_version=job['document_version_id'],parser_config={'configuration':parsed['configuration']}))
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        # Content-free failure; preserve the stale assessment and private artifact.
        pass
    async with engine.begin() as connection:
        return await repository.finish(connection,job_id,UUID(job['lease_token']),assessment)
