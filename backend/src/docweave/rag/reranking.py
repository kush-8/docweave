"""Validate reranked evidence and apply its token and item budgets."""

from docweave.rag.contracts import RetrievalError


def ranked_evidence(candidates, ordered_ids, count_tokens):
    by_id = {str(hit["chunk_id"]): hit for hit in candidates}
    if (len(candidates) > 20 or not isinstance(ordered_ids, list)
        or any(type(identity) is not str or identity not in by_id for identity in ordered_ids)
        or len(set(ordered_ids)) != len(ordered_ids)):
        raise RetrievalError("invalid_ranking")
    selected, used = [], 0
    for identity in ordered_ids:
        hit = by_id[identity]
        tokens = count_tokens(hit["quote"])
        if type(tokens) is not int or tokens < 0:
            raise RetrievalError("invalid_token_count")
        if used + tokens > 6000:
            continue
        selected.append(hit)
        used += tokens
        if len(selected) == 8:
            break
    return selected
