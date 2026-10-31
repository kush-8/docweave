"""Embedding batches preserve snapshot checks, bounds, and raw vector values."""

import pytest

from docweave.rag.contracts import RetrievalError
from docweave.rag.embeddings import embed_spans

pytestmark = pytest.mark.anyio


async def test_embedding_batches_recheck_before_each_dispatch_and_keep_source_spans():
    parsed = {"text": "x" * 65, "chunks": [{"start": i, "end": i + 1, "heading": None} for i in range(65)]}
    events = []
    vector = [1.0] + [0.0] * 767
    async def current():
        events.append("check")
        return {"version_id": "snapshot"}
    async def embed(bodies):
        events.append(len(bodies))
        return [vector for _ in bodies]
    rows = await embed_spans(parsed, {"version_id": "snapshot"}, embed, current)
    assert events == ["check", 64, "check", 1]
    assert len(rows) == 65
    assert rows[-1] == {**parsed["chunks"][-1], "content": "x", "embedding": vector}


async def test_changed_snapshot_blocks_the_next_embedding_batch():
    parsed = {"text": "x" * 65, "chunks": [{"start": i, "end": i + 1} for i in range(65)]}
    calls = []
    async def current():
        return {"version_id": "snapshot" if not calls else "changed"}
    async def embed(bodies):
        calls.append(bodies)
        return [[1.0] + [0.0] * 767 for _ in bodies]
    with pytest.raises(RetrievalError, match="snapshot_unavailable"):
        await embed_spans(parsed, {"version_id": "snapshot"}, embed, current)
    assert len(calls) == 1


@pytest.mark.parametrize("vectors", [None, [], [[0.0] * 768]])
async def test_embedding_batch_rejects_missing_or_invalid_vectors(vectors):
    async def current():
        return {"version_id": "snapshot"}
    async def embed(bodies):
        return vectors
    with pytest.raises(RetrievalError, match="invalid_vector"):
        await embed_spans({"text": "x", "chunks": [{"start": 0, "end": 1}]}, {"version_id": "snapshot"}, embed, current)
