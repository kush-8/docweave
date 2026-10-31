"""Gemini embedding request encoding and validated response decoding."""

from docweave.rag.contracts import HostedError, RetrievalError, validate_vector


def embedding_request(content, kind):
    if kind not in ("query", "document") or not isinstance(content, str) or not content.strip() or "\x00" in content:
        raise HostedError("invalid_embedding_input")
    prefix = "task: search result | query: " if kind == "query" else "title: none | text: "
    if len((prefix + content).encode("utf-8")) > 8192:
        raise HostedError("embedding_input_too_large")
    return {"model": "models/gemini-embedding-2", "content": {"parts": [{"text": prefix + content}]}, "outputDimensionality": 768}

def embedding_result(response):
    try:
        values = response["embedding"]["values"]
        validate_vector(values)
    except (KeyError, TypeError, RetrievalError):
        raise HostedError("invalid_embedding_response") from None
    return values
