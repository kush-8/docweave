"""Private, hash-bound publisher snapshots for release-label review; no model calls."""
import hashlib
import inspect
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from docweave.evaluation.reports import write_report
from docweave.integrations.parser import container_parse
from docweave.integrations.public_sources import fetch_document, MAX_RESPONSE
from docweave.rag.parsing import parse_text


def read_bounded(path, maximum):
    if path.is_symlink() or path.is_junction():
        raise ValueError('Snapshot links are unsupported')
    with path.open('rb') as file:
        raw = file.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Oversized snapshot')
    return raw


async def freeze_sources(dataset, registry, folder, *, fetcher=fetch_document, parser=container_parse):
    if dataset.model_dump_json() != dataset._validated_json:
        raise ValueError('Dataset changed after validation')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    registered = {page['url']: entry for entry in registry['entries'] for page in entry['pages']}
    manifest = {'format': 'release-sources-v1', 'dataset_sha256': dataset._sha256,
        'registry_sha256': hashlib.sha256(json.dumps(registry, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'created_at': datetime.now(timezone.utc).isoformat(), 'complete': False, 'sources': {}}
    for url in sorted({url for case in dataset.cases for url in case.sources}):
        receipt = {'outcome': 'unapproved'}
        manifest['sources'][url] = receipt
        entry = registered.get(url)
        if entry is not None and url.startswith(entry['publisher_root']):
            try:
                parts = urlsplit(url)
                selection = {'source_url': url, 'origin': f'https://{parts.hostname}',
                    'path_prefix': parts.path, 'attribution': entry['attribution']}
                raw, media = await fetcher(selection)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError('Oversized source')
                parsed = parser(raw, media)
                if inspect.isawaitable(parsed):
                    parsed = await parsed
                if parsed != parse_text(raw, media):
                    raise ValueError('Isolated parser differs from current implementation')
                identity = hashlib.sha256(url.encode()).hexdigest()
                (folder / (identity + '.body')).write_bytes(raw)
                write_report(folder / (identity + '.json'), parsed)
                receipt.update(outcome='frozen', raw_sha256=hashlib.sha256(raw).hexdigest(),
                    normalized_sha256=parsed['sha256'], media_type=media, body_file=identity + '.body',
                    parsed_file=identity + '.json', attribution=entry['attribution'])
            except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
                receipt.update(outcome='failed', reason=type(error).__name__, detail=str(error)[:256])
        write_report(folder / 'manifest.json', manifest)
    manifest['complete'] = all(row['outcome'] == 'frozen' for row in manifest['sources'].values())
    write_report(folder / 'manifest.json', manifest)
    return manifest


def load_frozen_sources(dataset, folder):
    if dataset.model_dump_json() != dataset._validated_json:
        raise ValueError('Dataset changed after validation')
    folder = Path(folder)
    manifest = json.loads(read_bounded(folder / 'manifest.json', 1024 * 1024))
    wanted = {url for case in dataset.cases for url in case.sources}
    if (not isinstance(manifest, dict) or manifest.get('format') != 'release-sources-v1' or
        manifest.get('dataset_sha256') != dataset._sha256 or not isinstance(manifest.get('sources'), dict) or set(manifest['sources']) != wanted):
        raise ValueError('Snapshot dataset binding differs')
    if any(not isinstance(row, dict) or row.get('outcome') not in ('frozen', 'failed', 'unapproved') for row in manifest['sources'].values()):
        raise ValueError('Invalid snapshot receipt')
    if manifest.get('complete') is not all(row.get('outcome') == 'frozen' for row in manifest['sources'].values()):
        raise ValueError('Inconsistent snapshot completion state')
    result = {}
    for url, receipt in manifest['sources'].items():
        if receipt['outcome'] != 'frozen':
            continue
        identity = hashlib.sha256(url.encode()).hexdigest()
        if receipt['body_file'] != identity + '.body' or receipt['parsed_file'] != identity + '.json':
            raise ValueError('Invalid snapshot path')
        raw = read_bounded(folder / receipt['body_file'], MAX_RESPONSE)
        if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
            raise ValueError('Snapshot body hash differs')
        parsed = json.loads(read_bounded(folder / receipt['parsed_file'], 16 * 1024 * 1024))
        if parsed != parse_text(raw, receipt['media_type']) or parsed['sha256'] != receipt['normalized_sha256']:
            raise ValueError('Snapshot parsed content differs')
        result[url] = parsed
    return result


def prepare_support_review(dataset, folder):
    parsed = load_frozen_sources(dataset, folder)
    manifest = read_bounded(Path(folder) / 'manifest.json', 1024 * 1024)
    review = {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': hashlib.sha256(manifest).hexdigest(),
        'human_review': 'pending', 'cases': {case.id: [] for case in dataset.cases}}
    for case in dataset.cases:
        for index, fact in enumerate(case.required_facts):
            words = set(re.findall(r'\w{4,}', fact.casefold()))
            candidates = []
            for url in case.sources:
                if url not in parsed:
                    continue
                for chunk in parsed[url]['chunks']:
                    quote = parsed[url]['text'][chunk['start']:chunk['end']]
                    overlap = len(words.intersection(re.findall(r'\w{4,}', quote.casefold())))
                    if overlap:
                        candidates.append((overlap, {'fact_index': index, 'source_url': url,
                            'start': chunk['start'], 'end': chunk['end'], 'quote': quote}))
            if candidates:
                review['cases'][case.id].append(max(candidates, key=lambda pair: pair[0])[1])
    return review


def validate_support_review(dataset, folder, review):
    parsed = load_frozen_sources(dataset, folder)
    manifest = read_bounded(Path(folder) / 'manifest.json', 1024 * 1024)
    if review.get('dataset_sha256') != dataset._sha256 or review.get('sources_manifest_sha256') != hashlib.sha256(manifest).hexdigest():
        raise ValueError('Support review binding differs')
    if review.get('human_review') not in ('pending', 'complete') or (review['human_review'] == 'complete' and
        (not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip())):
        raise ValueError('Human review identity is required')
    if set(review.get('cases', {})) != {case.id for case in dataset.cases}:
        raise ValueError('Support review cases differ')
    complete = True
    for case in dataset.cases:
        covered = set()
        for span in review['cases'][case.id]:
            index, url, start, end, quote = (span.get(key) for key in ('fact_index', 'source_url', 'start', 'end', 'quote'))
            if (type(index) is not int or not 0 <= index < len(case.required_facts) or url not in case.sources or url not in parsed
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(parsed[url]['text'])
                or not isinstance(quote, str) or not quote.strip() or parsed[url]['text'][start:end] != quote):
                raise ValueError('Invalid supporting span')
            covered.add(index)
        complete = complete and len(covered) == len(case.required_facts)
    all_sources = len(parsed) == len({url for case in dataset.cases for url in case.sources})
    return {'spans_complete': complete, 'all_sources_frozen': all_sources,
        'human_review': review['human_review'], 'eligible_for_evaluation': complete and all_sources and
        dataset.human_label_review == 'complete' and review['human_review'] == 'complete'}
