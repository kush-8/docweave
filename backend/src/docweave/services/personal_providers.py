"""One admitted hosted call, with irreversible uncertainty recorded before HTTP."""
import hashlib
import json
from decimal import Decimal
from uuid import UUID
from sqlalchemy.exc import DBAPIError
from docweave.integrations.provider_transport import provider_post
from docweave.rag.contracts import HostedError
from docweave.core.guardrails import assess_text
from docweave.repositories import personal_providers as repository

async def dispatch(payload,*,embedding,profile_id,operation_key,actor_id,project_id,engine,api_key,authorize,transport=None):
    assessment=assess_text(json.dumps(payload,ensure_ascii=False))
    if assessment.credential_blocked or not assessment.complete:
        raise HostedError('credential_blocked')
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if len(encoded)>131072 or not api_key:
        raise HostedError('provider_unavailable')
    # UTF-8 byte count conservatively bounds these ordinary-text payload tokens, including framing.
    incoming=len(encoded)+512
    outgoing=0 if embedding else payload.get('max_completion_tokens',4096)
    if type(outgoing) is not int or not 0<=outgoing<=16384:
        raise HostedError('invalid_output_bound')
    body_hash=hashlib.sha256(encoded).hexdigest()
    operation=hashlib.sha256((str(operation_key)+':'+body_hash).encode()).hexdigest()
    await authorize()
    try:
        async with engine.begin() as c:
            reservation=await repository.resume(c,project_id,actor_id,profile_id,operation,body_hash,incoming,outgoing,hashlib.sha256(str(operation_key).encode()).hexdigest())
    except DBAPIError as error:
        code=getattr(error.orig,'sqlstate',None)
        raise HostedError('completion_unknown' if code=='DW014' else 'provider_unavailable') from None
    if 'response' in reservation:
        await authorize()
        return reservation['response']
    expected=reservation['model']
    actual_model=payload.get('model','').removeprefix('models/')
    if actual_model!=expected or (reservation['role']=='embedding') != embedding or reservation['provider']!=('gemini' if embedding else 'groq'):
        raise HostedError('profile_mismatch')
    await authorize()
    try:
        result=await provider_post(embedding,encoded,api_key,transport=transport)
    except Exception:
        # Retain the conservative charge and never infer whether the provider completed.
        raise HostedError('completion_unknown') from None
    usage=result.get('usage',{}) if not embedding else result.get('usageMetadata',{})
    in_count=usage.get('prompt_tokens') if not embedding else usage.get('promptTokenCount')
    out_count=usage.get('completion_tokens',0) if not embedding else 0
    if type(in_count) is int and type(out_count) is int and in_count>=0 and out_count>=0:
        actual=(Decimal(in_count)*Decimal(reservation['input_rate'])+Decimal(out_count)*Decimal(reservation['output_rate']))/1000000+Decimal(reservation['fixed_usd'])
        async with engine.begin() as c:
            await repository.settle(c,UUID(reservation['id']),actual)
    await authorize()
    async with engine.begin() as c:
        await repository.checkpoint(c,UUID(reservation['id']),result)
    await authorize()
    return result
