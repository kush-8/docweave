import pytest

from docweave.core import guardrails


def test_langchain_scan_is_local_untraced_and_returns_only_rule_ids(monkeypatch):
    from langchain_core.runnables import RunnableSequence
    from langsmith import tracing_context
    assert isinstance(getattr(guardrails, 'GUARDRAIL_CHAIN', None), RunnableSequence)
    seen=[]
    original=RunnableSequence.invoke
    def invoke(self, value, *args, **kwargs):
        from langsmith.run_helpers import get_tracing_context
        seen.append(get_tracing_context()['enabled'])
        return original(self, value, *args, **kwargs)
    monkeypatch.setattr(RunnableSequence, 'invoke', invoke)
    secret='ghp_'+'a'*36
    with tracing_context(enabled=True):
        result=guardrails.assess_text(secret)
    assert seen==[False]
    assert result.credential_blocked and result.findings==('github-token',)
    assert secret not in repr(result)


def test_revision_is_bound_to_detector_configuration():
    assert guardrails.RULE_REVISION.startswith('deterministic-')
    assert len(guardrails.RULE_REVISION)==len('deterministic-')+64


def test_retained_completed_turn_is_checked_under_current_rules():
    from docweave.services.guardrails import release_turn
    turn={'status':'completed','message':'Explain hooks','answer':'ghp_'+'a'*36,'citations':[]}
    released=release_turn(turn)
    assert released['status']=='blocked_policy' and released['answer'] is None and released['message']==''
    assert turn['status']=='completed'


@pytest.mark.anyio
async def test_history_is_rechecked_after_it_was_cached(monkeypatch):
    from docweave.services.answer_engine import AnswerEngine
    from docweave.rag.contracts import HostedError
    from contextlib import asynccontextmanager
    from uuid import uuid4
    @asynccontextmanager
    async def begin():
        yield None
    class Engine:
        pass
    engine=Engine()
    engine.begin=begin
    items=[{'status':'completed','message':'question','answer':'answer','context_revision':1}]
    async def history(*args):
        return items
    monkeypatch.setattr('docweave.services.answer_engine.repository.history',history)
    async def policy(*args):
        return {'epoch':1}
    monkeypatch.setattr('docweave.services.answer_engine.current_policy',policy)
    monkeypatch.setattr('docweave.services.answer_engine.count_evidence_tokens',len)
    async def authorized():
        pass
    job={'id':str(uuid4()),'lease_token':str(uuid4()),'actor_id':str(uuid4()),'project':{'id':str(uuid4())}}
    answerer=AnswerEngine(job,engine=engine,read_engine=None,config={},generation_id=None,authorize=authorized)
    await answerer.context_history()
    items[0]={**items[0],'status':'blocked_policy','answer':None}
    with pytest.raises(HostedError,match='context_blocked'):
        await answerer.authorize()
