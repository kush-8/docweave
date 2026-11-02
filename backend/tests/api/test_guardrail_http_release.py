"""Policy changes during upstream HTTP cannot authorize an old scanner's release."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
import pytest
from docweave.core.errors import DomainError
from docweave.rag.contracts import HostedError

pytestmark=pytest.mark.anyio


@pytest.fixture
def release(monkeypatch):
    from docweave.api.routes import personal,conversations
    state={'changed':False}
    @asynccontextmanager
    async def session(*args):
        yield None
    async def policy(*args):
        if state['changed']:
            raise HostedError('guardrail_changed')
        return {'epoch':1}
    async def upstream(*args):
        state['changed']=True
    async def project(*args):
        return {'repository':{'repository_id':42}}
    monkeypatch.setattr(personal,'domain_session',session)
    monkeypatch.setattr(conversations,'domain_session',session)
    monkeypatch.setattr(personal,'current_policy',policy)
    monkeypatch.setattr(personal.repository,'project',project)
    monkeypatch.setattr(personal,'github_service',lambda *args:(None,None,SimpleNamespace(repository=upstream)))
    monkeypatch.setattr(conversations,'github_service',lambda *args:(None,None,None))
    return state,SimpleNamespace(state=SimpleNamespace(github_token='fixture')),{'id':str(uuid4())}


async def test_project_release_fences_rule_change_during_github(release):
    from docweave.api.routes.personal import project_access
    state,request,user=release
    with pytest.raises(DomainError,match='not_ready'):
        await project_access(request,user,uuid4())


async def test_turn_read_fences_actual_release_after_upstream_access(release,monkeypatch):
    from docweave.api.routes import conversations
    state,request,user=release
    async def turn(*args):
        return {'conversation_id':str(uuid4()),'status':'completed','answer':'Old no-citation answer','citations':[]}
    async def access(*args):
        state['changed']=True
    monkeypatch.setattr(conversations.repository,'turn',turn)
    monkeypatch.setattr(conversations,'conversation_access',access)
    with pytest.raises(DomainError,match='not_ready'):
        await conversations.turn(uuid4(),request,user)


async def test_idempotent_append_applies_completed_answer_guard(release,monkeypatch):
    from docweave.api.routes import conversations
    state,request,user=release
    async def access(*args):
        pass
    async def append(*args):
        return {'status':'completed','message':'Question','answer':'ghp_'+'a'*36,'citations':[]}
    monkeypatch.setattr(conversations,'conversation_access',access)
    monkeypatch.setattr(conversations.repository,'append_turn',append)
    result=await conversations.append_turn(uuid4(),SimpleNamespace(idempotency_key=uuid4(),message='Question'),request,user)
    assert result['status']=='blocked_policy' and result['answer'] is None and result['citations']==[]
