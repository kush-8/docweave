"""Batch embedding coordination with a fresh snapshot check before each call."""

from docweave.rag.contracts import RetrievalError, validate_vector


async def embed_spans(parsed, snapshot, embedder, current_snapshot):
    spans, rows = parsed["chunks"], []
    for start in range(0, len(spans), 64):
        current = await current_snapshot()
        if current["version_id"] != snapshot["version_id"]:
            raise RetrievalError("snapshot_unavailable")
        batch = spans[start:start + 64]
        bodies = [parsed["text"][span["start"]:span["end"]] for span in batch]
        vectors = await embedder(bodies)
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise RetrievalError("invalid_vector")
        for span, body, vector in zip(batch, bodies, vectors):
            validate_vector(vector)
            rows.append({**span, "content": body, "embedding": vector})
    return rows
