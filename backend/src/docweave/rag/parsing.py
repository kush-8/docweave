"""Bounded UTF-8 decoding and normalization for the isolated parser."""

import hashlib
from docweave.rag.contracts import CONFIGURATION, MAX_BYTES, MAX_CHARS
from docweave.rag.chunking import chunk_text


def parse_text(content: bytes, media_type: str) -> dict:
    if media_type not in ("text/plain", "text/markdown") or len(content) > MAX_BYTES:
        raise ValueError("Unsupported or oversized text")
    normalized = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) > MAX_CHARS or not normalized.strip() or any(ord(c) < 32 and c not in "\n\t" for c in normalized):
        raise ValueError("Invalid text")
    chunks = chunk_text(normalized, media_type)
    return {"text": normalized, "sha256": hashlib.sha256(normalized.encode()).hexdigest(), "chunks": chunks,
        "configuration": CONFIGURATION + ":" + media_type}
