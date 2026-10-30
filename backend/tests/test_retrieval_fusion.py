"""Hand-derived fusion and exact-span evidence limits; no hosted transport."""

from uuid import UUID

import pytest


def hit(number, quote="evidence"):
    return {"chunk_id": UUID(int=number), "quote": quote, "locator": {"start": 0, "end": len(quote)}, "score": 9.0}


def test_rrf_deduplicates_and_uses_original_channel_ranks_without_mutation():
    from docweave.retrieval import fuse_channels
    a, b, c = hit(1), hit(2), hit(3)
    fused = fuse_channels({"lexical": [a, b, a], "vector": [c, b]})
    assert [row["chunk_id"] for row in fused] == [b["chunk_id"], a["chunk_id"], c["chunk_id"]]
    assert fused[0]["score"] == pytest.approx(2 / 62)
    assert fused[1]["score"] == pytest.approx(1 / 61)
    assert a["score"] == 9.0 and fused[1]["locator"] == a["locator"]


def test_rrf_enforces_thirty_per_channel_twenty_for_reranking_and_stable_ties():
    from docweave.retrieval import fuse_channels
    result = fuse_channels({"lexical": [hit(i) for i in range(1, 36)], "vector": [hit(i) for i in range(101, 136)]})
    assert len(result) == 20
    assert [row["chunk_id"].int for row in result[:4]] == [1, 101, 2, 102]
    assert fuse_channels({"lexical": [], "vector": []}) == []


def test_ranked_evidence_keeps_exact_spans_with_eight_chunk_six_thousand_token_limits():
    from docweave.retrieval import ranked_evidence
    candidates = [hit(i, "x" * (6001 if i == 1 else 1000)) for i in range(1, 12)]
    result = ranked_evidence(candidates, [str(row["chunk_id"]) for row in candidates], len)
    assert result == candidates[1:7]
    small = [hit(i, "x") for i in range(1, 12)]
    assert ranked_evidence(small, [str(row["chunk_id"]) for row in small], len) == small[:8]
    assert ranked_evidence(small, [], len) == []


@pytest.mark.parametrize("identities", [[str(UUID(int=2))], [str(UUID(int=1))] * 2, "not-an-array", [1]])
def test_rerank_ids_must_be_unique_members_of_the_candidate_set(identities):
    from docweave.retrieval import RetrievalError, ranked_evidence
    with pytest.raises(RetrievalError, match="invalid_ranking"):
        ranked_evidence([hit(1)], identities, len)


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_evidence_token_counter_cannot_supply_an_invalid_bound(count):
    from docweave.retrieval import RetrievalError, ranked_evidence
    with pytest.raises(RetrievalError, match="invalid_token_count"):
        ranked_evidence([hit(1)], [str(UUID(int=1))], lambda _: count)
