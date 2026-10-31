"""Literal evidence token counts for the selected GPT-OSS family, excluding chat framing."""

import tiktoken

TOKENIZER = "tiktoken-0.12.0:o200k_harmony:ordinary-text"


def count_evidence_tokens(content):
    content.encode("utf-8", errors="strict")
    return len(tiktoken.get_encoding("o200k_harmony").encode_ordinary(content))
