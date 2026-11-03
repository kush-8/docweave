"""Retrieval recall metrics with explicit denominators."""

import json
import hashlib
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


def release_support_recall(dataset, folder, review, batch):
    """Micro Recall@10 over required facts with reviewed alternative supporting spans."""
    from docweave.evaluation.frozen import load_frozen_sources, validate_support_review
    if not validate_support_review(dataset, folder, review)['eligible_for_evaluation']:
        raise ValueError('Reviewed labels and supporting spans are required')
    if (not isinstance(batch, dict) or batch.get('dataset_sha256') != dataset._sha256
        or batch.get('sources_manifest_sha256') != review['sources_manifest_sha256']
        or not isinstance(batch.get('cases'), dict) or set(batch['cases']) != {case.id for case in dataset.cases}):
        raise ValueError('Every capture must bind the reviewed dataset and frozen sources')
    parsed = load_frozen_sources(dataset, folder)
    by_case = {}
    for case in dataset.cases:
        capture = batch['cases'][case.id]
        if not isinstance(capture, dict) or capture.get('case_id') != case.id:
            raise ValueError('Capture case identity differs')
        pipeline = capture.get('pipeline', {})
        if not isinstance(pipeline, dict) or not isinstance(pipeline.get('retrieved_top_10', []), list):
            raise ValueError('Invalid captured retrieval')
        matched = set()
        for hit in pipeline.get('retrieved_top_10', [])[:10]:
            if not isinstance(hit, dict) or not isinstance(hit.get('locator'), dict):
                raise ValueError('Invalid retrieved span')
            start, end = hit['locator'].get('start'), hit['locator'].get('end')
            url, quote = hit.get('source_url'), hit.get('quote')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end
                or not isinstance(quote, str) or not quote.strip() or url is not None and not isinstance(url, str)):
                raise ValueError('Invalid retrieved span')
            if url not in parsed:
                continue
            text = parsed[url]['text']
            if end > len(text) or text[start:end] != quote:
                raise ValueError('Retrieved quote differs from its frozen source offsets')
            for span in review['cases'][case.id]:
                if span['source_url'] == url and start <= span['start'] < span['end'] <= end:
                    matched.add(span['fact_index'])
        denominator = len(case.required_facts)
        by_case[case.id] = {'value': len(matched)/denominator if denominator else None,
            'matched': len(matched), 'denominator': denominator}
    def aggregate(cases):
        matched = sum(by_case[case.id]['matched'] for case in cases)
        denominator = sum(by_case[case.id]['denominator'] for case in cases)
        return {'value': matched/denominator if denominator else None, 'matched': matched, 'denominator': denominator}
    return {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': review['sources_manifest_sha256'],
        'support_review_sha256': hashlib.sha256(json.dumps(review, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
        'captures_sha256': hashlib.sha256(json.dumps(batch, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False).encode()).hexdigest(),
        'denominator_unit': 'required_facts_with_reviewed_support', 'by_case': by_case,
        'overall': aggregate(dataset.cases),
        'by_split': {split: aggregate([case for case in dataset.cases if case.split == split]) for split in ('development', 'held_out')},
        'semantic_quality_evidence': False}
