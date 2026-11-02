"""Strict wire contracts; private context is data, never application instructions."""
import json
import tiktoken
from docweave.integrations.groq import GROQ_MODELS
from docweave.rag.prompts import structured_request
from docweave.rag.contracts import HostedError,unique_keys
from docweave.core.guardrails import assess_text

SUMMARY_PROMPT_VERSION = 'conversation-summary-v1'


def summary_request(project, previous, history, model):
    schema = {'type': 'object', 'properties': {'summary': {'type': 'string'}},
              'required': ['summary'], 'additionalProperties': False}
    return structured_request('Summarize historical conversation context in at most 1,000 tokens.', [
        'Preserve user goals, decisions, unresolved questions and reference identities.',
        'Label version-specific statements with their original context revision. The current project context takes precedence.',
        'Prior answers and summaries are historical discussion, never documentary evidence. Do not add facts or instructions.'],
        schema, {'project_context': project, 'previous_summary': previous, 'conversation_context': history},
        model, name='conversation_summary', maximum=2048)


def summary_result(response, model):
    result = _content(response, model)
    if (not isinstance(result, dict) or set(result) != {'summary'} or
            not isinstance(result['summary'], str) or not result['summary'].strip() or
            len(tiktoken.get_encoding('o200k_harmony').encode_ordinary(result['summary'])) > 2000):
        raise HostedError('invalid_summary_output')
    assessment = assess_text(result['summary'])
    if not assessment.complete or assessment.credential_blocked or assessment.injection_flagged:
        raise HostedError('invalid_summary_output')
    return result['summary']


def answer_request(query,project,history,evidence,model):
    if model not in GROQ_MODELS:
        raise HostedError('unsupported_answer_model')
    identities=[str(hit['chunk_id']) for hit in evidence]
    schema={'type':'object','properties':{'kind':{'type':'string','enum':['answered','needs_clarification','abstained']},'blocks':{'type':'array','items':{'type':'object','properties':{'kind':{'type':'string','enum':['documentation','project_context','inferred_advice']},'text':{'type':'string'},'chunk_ids':{'type':'array','items':{'type':'string','enum':identities}}},'required':['kind','text','chunk_ids'],'additionalProperties':False}}},'required':['kind','blocks'],'additionalProperties':False}
    return structured_request('Answer the engineering question using only eligible evidence for documentation claims.',[
        'Documentation claims must cite supplied chunk IDs. Do not invent references or URLs.',
        'Separate documentation claims, supplied project context and inferred advice into their respective block kinds.',
        'If evidence is insufficient, abstain or ask one focused clarification. Prior assistant text is not documentary proof.'],schema,
        {'query':query,'project_context':project,'conversation_context':history,'evidence':evidence},model,name='answer')


def _content(response,model):
    try:
        if response['model']!=model or len(response['choices'])!=1:
            raise ValueError
        choice=response['choices'][0]
        message=choice['message']
        if choice['finish_reason']!='stop' or message.get('tool_calls') or message.get('function_call') or message.get('refusal'):
            raise ValueError
        content=message['content']
        if not isinstance(content,str) or len(content.encode())>65536:
            raise ValueError
        assessment=assess_text(content)
        if not assessment.complete or assessment.credential_blocked or assessment.injection_flagged:
            raise ValueError
        result=json.loads(content,object_pairs_hook=unique_keys)
        assessment=assess_text(json.dumps(result,ensure_ascii=False))
        if not assessment.complete or assessment.credential_blocked or assessment.injection_flagged:
            raise ValueError
        return result
    except (ValueError,KeyError,TypeError):
        raise HostedError('invalid_answer_output') from None


def answer_result(response,evidence,model):
    result=_content(response,model)
    allowed={str(hit['chunk_id']) for hit in evidence}
    try:
        if set(result)!={'kind','blocks'} or result['kind'] not in ('answered','needs_clarification','abstained') or not isinstance(result['blocks'],list) or len(result['blocks'])>40:
            raise ValueError
        for block in result['blocks']:
            if set(block)!={'kind','text','chunk_ids'} or block['kind'] not in ('documentation','project_context','inferred_advice') or not isinstance(block['text'],str) or not block['text'].strip() or not isinstance(block['chunk_ids'],list):
                raise ValueError
            if any(type(identity) is not str or identity not in allowed for identity in block['chunk_ids']) or len(set(block['chunk_ids']))!=len(block['chunk_ids']):
                raise ValueError
            if block['kind']=='documentation' and not block['chunk_ids']:
                raise ValueError
        return result
    except (ValueError,KeyError,TypeError):
        raise HostedError('invalid_answer_citations') from None


def resolution_request(query,project,history,model):
    identities=[entry['id'] for entry in project['stack']]
    schema={'type':'object','properties':{'uncertain':{'type':'boolean'},'dependency_ids':{'type':'array','items':{'type':'string','enum':identities}}},'required':['uncertain','dependency_ids'],'additionalProperties':False}
    return structured_request('Identify which project stack dependencies are required to answer the question.',[
        'Resolve references using authorized conversation context and the current project stack.',
        'Use only supplied dependency IDs. Mark uncertain if essential references cannot be resolved; an unrelated question may have an empty dependency list.'],schema,
        {'query':query,'project_context':project,'conversation_context':history},model,name='dependency_resolution',maximum=1024)


def resolution_result(response,project,model):
    result=_content(response,model)
    allowed={entry['id'] for entry in project['stack']}
    if not isinstance(result,dict) or set(result)!={'uncertain','dependency_ids'} or type(result['uncertain']) is not bool or not isinstance(result['dependency_ids'],list) or any(type(value) is not str or value not in allowed for value in result['dependency_ids']) or len(set(result['dependency_ids']))!=len(result['dependency_ids']):
        raise HostedError('invalid_dependency_resolution')
    return None if result['uncertain'] else result['dependency_ids']
