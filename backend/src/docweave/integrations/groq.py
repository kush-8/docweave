"""Groq ranking request encoding and validated response decoding."""

import json
from uuid import UUID
from docweave.rag.contracts import HostedError, unique_keys
from docweave.rag.prompts import ranking_schema, ranking_system


GROQ_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")

def ranking_request(query, candidates, model):
    if model not in GROQ_MODELS or not isinstance(query, str) or not query.strip() or len(query) > 4096:
        raise HostedError("invalid_ranking_input")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 20:
        raise HostedError("invalid_candidates")
    try:
        identities = [candidate["chunk_id"] for candidate in candidates]
        if any(type(identity) is not str or str(UUID(identity)) != identity for identity in identities) or len(set(identities)) != len(identities):
            raise ValueError
        envelope = json.dumps({"query": query, "project_context": {}, "conversation_context": [], "evidence": candidates}, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, KeyError):
        raise HostedError("invalid_candidates") from None
    if len(envelope.encode("utf-8")) > 98304:
        raise HostedError("ranking_input_too_large")
    schema = ranking_schema(identities)
    return {"model": model, "messages": [
        {"role": "system", "content": ranking_system(schema)},
        {"role": "user", "content": envelope}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "ranking", "strict": True, "schema": schema}},
        "max_completion_tokens": 4096, "reasoning_effort": "low", "temperature": 0, "stream": False}

def ranking_result(response, candidate_ids, model):
    try:
        if model not in GROQ_MODELS or response["model"] != model or len(response["choices"]) != 1:
            raise ValueError
        choice = response["choices"][0]
        message = choice["message"]
        if choice["finish_reason"] != "stop" or message.get("tool_calls") or message.get("function_call") or message.get("refusal"):
            raise ValueError
        content = message["content"]
        if not isinstance(content, str) or len(content.encode("utf-8")) > 65536:
            raise ValueError
        result = json.loads(content, object_pairs_hook=unique_keys)
        if not isinstance(result, dict) or set(result) != {"ordered_chunk_ids"}:
            raise ValueError
        identities = result["ordered_chunk_ids"]
        if not isinstance(identities, list) or len(identities) > 20 or any(type(identity) is not str or identity not in candidate_ids for identity in identities) or len(set(identities)) != len(identities):
            raise ValueError
        usage = response["usage"]
        incoming, outgoing, total = (usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
        reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        if any(type(value) is not int or value < 0 for value in (incoming, outgoing, total)) or incoming > 131072 or outgoing > 4096 or total != incoming + outgoing:
            raise ValueError
        if reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= outgoing):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HostedError("invalid_ranking_response") from None
    return {"ordered_chunk_ids": identities, "input_tokens": incoming, "output_tokens": outgoing, "reasoning_tokens": reasoning}
