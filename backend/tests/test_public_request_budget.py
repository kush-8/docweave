import json
from uuid import UUID
from docweave.rag.tokenization import count_evidence_tokens


def test_reranking_keeps_whole_chunks_within_the_free_account_request_window():
    from docweave.rag.reranking import bounded_ranking_request
    candidates = [{"chunk_id": str(UUID(int=i)), "document_version_id": str(UUID(int=100 + i)), "quote": "content " * 500} for i in range(1, 21)]
    payload, accepted = bounded_ranking_request("connection configuration", candidates)
    assert 0 < len(accepted) < 20
    assert count_evidence_tokens(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)) <= 3000
    assert all(hit in candidates for hit in accepted)


def test_rate_limit_wait_uses_observed_token_capacity_and_reset():
    from docweave.services.public_pilot import quota_delay
    assert quota_delay({"x-ratelimit-remaining-tokens": "7500"}) == 2.1
    assert quota_delay({"x-ratelimit-remaining-tokens": "100", "x-ratelimit-reset-tokens": "1m2.5s"}) == 63.5
    assert quota_delay({}) == 61
