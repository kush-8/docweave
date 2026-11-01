import copy
import pytest


def manifest():
    return {'entries': [{'technology': 'httpx', 'ecosystem': 'python', 'docs_target': '0.28.1',
        'coverage': {'granularity': 'exact', 'version': '0.28.1'}, 'package_aliases': [],
        'origin': 'https://raw.githubusercontent.com', 'path_prefix': '/encode/httpx/0.28.1/docs/',
        'source_url': 'https://raw.githubusercontent.com/encode/httpx/0.28.1/docs/quickstart.md',
        'attribution': 'HTTPX authors, BSD-3-Clause; QuickStart page only.', 'source_hash': 'a' * 64}]}


def test_manifest_review_digest_binds_exact_source_coverage_and_attribution():
    from docweave.services.catalog_review import parse_manifest
    entries, digest = parse_manifest(manifest())
    changed = copy.deepcopy(manifest())
    changed['entries'][0]['coverage']['version'] = '0.29.0'
    with pytest.raises(ValueError):
        parse_manifest(changed)
    changed = copy.deepcopy(manifest())
    changed['entries'][0]['source_hash'] = 'b' * 64
    assert parse_manifest(changed)[1] != digest
    assert len(digest) == 64 and len(entries) == 1


@pytest.mark.parametrize('url', ['http://example.org/guide.md', 'https://127.0.0.1/guide.md',
    'https://user:secret@raw.githubusercontent.com/encode/httpx/0.28.1/docs/quickstart.md',
    'https://raw.githubusercontent.com/encode/httpx/0.28.1/docs/../private.md',
    'https://raw.githubusercontent.com/encode/httpx/0.28.1/docs/quickstart.md?token=secret'])
def test_manifest_rejects_unsafe_or_out_of_scope_sources(url):
    from docweave.services.catalog_review import parse_manifest
    data = manifest()
    data['entries'][0]['source_url'] = url
    with pytest.raises(ValueError):
        parse_manifest(data)
