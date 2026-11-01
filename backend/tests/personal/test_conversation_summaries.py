"""Summary reuse and rebuilding without paid provider calls."""
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from docweave.services.answer_engine import AnswerEngine
from docweave.rag.contracts import HostedError

pytestmark = pytest.mark.anyio


class Engine:
    @asynccontextmanager
    async def begin(self):
        yield None


@pytest.fixture
def memory(monkeypatch):
    items = [{'sequence': n, 'status': 'completed', 'message': 'Earlier question ' * 900,
              'answer': 'Earlier answer ' * 900, 'context_revision': 1} for n in range(1, 5)]
    stored = []
    calls = []
    async def history(*args):
        return items
    async def summary(*args):
        if len(args) == 5:
            stored[:] = [args[-1]]
        return stored[0] if stored else None
    monkeypatch.setattr('docweave.services.answer_engine.repository.history', history)
    monkeypatch.setattr('docweave.services.answer_engine.repository.summary', summary, raising=False)
    async def authorize():
        pass
    def pipeline(revision=1):
        job = {'id': str(uuid4()), 'lease_token': str(uuid4()), 'actor_id': str(uuid4()),
               'project': {'id': str(uuid4()), 'context_revision': revision}, 'conversation': {}}
        result = AnswerEngine(job, engine=Engine(), read_engine=None,
                              config={'SUMMARY_PROFILE_ID': 'summary-profile'}, generation_id=None, authorize=authorize)
        async def profile(identity, role):
            assert identity == 'summary-profile' and role == 'summarization'
            return {'model': 'openai/gpt-oss-20b'}
        async def dispatch(payload, profile, stage):
            calls.append(payload)
            assert stage == 'summarization'
            return {'model': profile['model'], 'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps({'summary': 'Earlier discussion concerned React on historical revision 1.'})}}]}
        result.profile = profile
        result.dispatch = dispatch
        return result
    return items, stored, calls, pipeline


async def test_summary_survives_new_worker_and_rebuilds_for_context_revision(memory):
    items, stored, calls, pipeline = memory
    first = await pipeline().context_history()
    assert first[0]['summary'] and stored[0]['context_revision'] == 1
    assert stored[0]['through_sequence'] > 0
    count = len(calls)
    assert await pipeline().context_history() == first
    assert len(calls) == count
    await pipeline(2).context_history()
    assert stored[0]['context_revision'] == 2 and len(calls) > count
    # Rebuilding starts from authorized turns, never the stale summary.
    assert json.loads(calls[count]['messages'][1]['content'])['previous_summary'] == ''


async def test_summary_rebuilds_when_covered_history_or_prompt_changes(memory):
    items, stored, calls, pipeline = memory
    await pipeline().context_history()
    items[0]['answer'] = 'Corrected historical answer'
    count = len(calls)
    await pipeline().context_history()
    assert len(calls) > count
    stored[0]['prompt_version'] = 'obsolete'
    count = len(calls)
    await pipeline().context_history()
    assert len(calls) > count


async def test_blocked_history_cannot_reuse_summary_and_cached_history_is_rechecked(memory):
    items, stored, calls, pipeline = memory
    worker = pipeline()
    await worker.context_history()
    count = len(calls)
    items[0]['status'] = 'blocked_policy'
    with pytest.raises(HostedError, match='context_blocked'):
        await pipeline().context_history()
    with pytest.raises(HostedError):
        await worker.authorize()
    assert len(calls) == count


async def test_short_history_needs_no_summary_profile_or_provider(memory):
    items, stored, calls, pipeline = memory
    items[:] = [dict(items[0], message='Hi', answer='Hello')]
    assert await pipeline().context_history() == [
        {'message': 'Hi', 'answer': 'Hello', 'context_revision': 1}]
    assert not stored and not calls
