"""Deterministic reciprocal-rank fusion of the existing retrieval channels."""

def fuse_channels(channels):
    hits, scores = {}, {}
    for name in ("lexical", "vector"):
        seen = set()
        for rank, hit in enumerate(channels[name][:30], 1):
            identity = hit["chunk_id"]
            if identity in seen:
                continue
            seen.add(identity)
            hits.setdefault(identity, hit)
            scores[identity] = scores.get(identity, 0) + 1 / (60 + rank)
    ordered = sorted(hits, key=lambda identity: (-scores[identity], str(identity)))
    return [{**hits[identity], "score": scores[identity]} for identity in ordered[:20]]
