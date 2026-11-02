import json
import pytest
from tests.evaluation.test_release_preparation import draft, save
from docweave.evaluation.release import load_release_dataset
from docweave.rag.parsing import parse_text

pytestmark = pytest.mark.anyio


async def test_freeze_pins_registered_bytes_and_detects_tampering(tmp_path):
    from docweave.evaluation.frozen import freeze_sources, load_frozen_sources
    dataset = load_release_dataset(save(tmp_path, draft()))
    registry = {'entries': [{'id': 'example', 'publisher_root': 'https://example.test/',
        'attribution': 'Example publisher', 'pages': [{'url': 'https://example.test/docs'}]}]}
    async def fetch(selection):
        assert selection['path_prefix'] == '/docs'
        return b'# Guide\n\nKeep credentials on the backend.\n', 'text/markdown'
    folder = tmp_path / 'frozen'
    manifest = await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    assert manifest['sources']['https://example.test/docs']['outcome'] == 'frozen'
    parsed = load_frozen_sources(dataset, folder)
    assert parsed['https://example.test/docs']['text'] == '# Guide\n\nKeep credentials on the backend.\n'
    from docweave.evaluation.frozen import prepare_support_review, validate_support_review
    review = prepare_support_review(dataset, folder)
    assert review['human_review'] == 'pending'
    status = validate_support_review(dataset, folder, review)
    assert status['spans_complete'] is True and status['eligible_for_evaluation'] is False
    assert review['cases']['case-0'][0]['quote'] == '# Guide\n\nKeep credentials on the backend.\n'
    review['cases']['case-0'][0]['quote'] = 'Invented evidence'
    with pytest.raises(ValueError, match='span'): validate_support_review(dataset, folder, review)
    review = prepare_support_review(dataset, folder)
    review['human_review'] = 'complete'
    review['reviewer'] = ''
    with pytest.raises(ValueError, match='identity'): validate_support_review(dataset, folder, review)
    review['reviewer'] = 'Reviewer'
    assert validate_support_review(dataset, folder, review)['eligible_for_evaluation'] is False
    manifest['sources']['https://example.test/docs']['attribution'] = 'Changed metadata'
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='binding'): validate_support_review(dataset, folder, review)
    manifest['sources']['https://example.test/docs']['outcome'] = 'failed'
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='completion'): load_frozen_sources(dataset, folder)
    manifest['sources']['https://example.test/docs']['outcome'] = 'frozen'
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    snapshot = folder / manifest['sources']['https://example.test/docs']['body_file']
    snapshot.write_bytes(b'Changed source')
    with pytest.raises(ValueError, match='hash'): load_frozen_sources(dataset, folder)


async def test_unregistered_reference_is_not_fetched_or_silently_substituted(tmp_path):
    from docweave.evaluation.frozen import freeze_sources
    dataset = load_release_dataset(save(tmp_path, draft()))
    async def fetch(selection):
        raise AssertionError('An unapproved reference must not be fetched')
    manifest = await freeze_sources(dataset, {'entries': []}, tmp_path / 'frozen', fetcher=fetch, parser=parse_text)
    assert manifest['sources']['https://example.test/docs']['outcome'] == 'unapproved'
    assert manifest['complete'] is False


async def test_failed_freeze_is_recorded_and_existing_snapshot_is_not_overwritten(tmp_path):
    from docweave.evaluation.frozen import freeze_sources
    dataset = load_release_dataset(save(tmp_path, draft()))
    registry = {'entries': [{'id': 'example', 'publisher_root': 'https://example.test/',
        'attribution': 'Example publisher', 'pages': [{'url': 'https://example.test/docs'}]}]}
    async def fetch(selection):
        raise OSError('Network unavailable')
    folder = tmp_path / 'frozen'
    manifest = await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    assert manifest['sources']['https://example.test/docs']['outcome'] == 'failed'
    original = (folder / 'manifest.json').read_bytes()
    with pytest.raises(FileExistsError): await freeze_sources(dataset, registry, folder, fetcher=fetch, parser=parse_text)
    assert (folder / 'manifest.json').read_bytes() == original
