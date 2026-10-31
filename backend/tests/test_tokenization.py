from docweave.rag.tokenization import count_evidence_tokens


def test_harmony_counts_real_subwords_and_keeps_role_tags_literal():
    assert count_evidence_tokens("Hello, world!") == 4
    assert count_evidence_tokens("<|start|>") > 1
    assert count_evidence_tokens("x_" * 100) > 100
