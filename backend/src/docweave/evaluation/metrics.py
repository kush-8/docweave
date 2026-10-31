"""Retrieval recall metrics with explicit denominators."""

import json
from docweave.evaluation.config import CORPUS


def ann_recall(exact, approximate, k):
    reference = set(exact[:k])
    matched = len(reference.intersection(approximate[:k]))
    return {"value": matched / len(reference) if reference else None, "matched": matched, "denominator": len(reference)}

def support_recall(case, hits):
    documents = {item["file"]: item for item in json.loads((CORPUS / "manifest.json").read_text())["documents"]}
    matched = 0
    for support in case.supports:
        source_url = documents[support.file]["source_url"]
        for hit in hits[:10]:
            same_source = hit["provenance"].get("document_title") == support.file or (source_url and hit["source_url"] == source_url)
            if same_source and support.quote in hit["quote"] and hit["locator"]["start"] <= support.start < support.end <= hit["locator"]["end"]:
                matched += 1
                break
    return {"value": matched / len(case.supports) if case.supports else None, "matched": matched, "denominator": len(case.supports)}
