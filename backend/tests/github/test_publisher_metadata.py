import json

import pytest

from docweave.integrations import publisher_metadata as publisher
from docweave.core.errors import DomainError


@pytest.fixture(autouse=True)
def inline_transport(monkeypatch):
    async def inline(function, *args):
        return function(*args)
    monkeypatch.setattr(publisher.asyncio, 'to_thread', inline)


def run(coroutine):
    # These unit tests have only immediate mocked I/O; avoid Windows socketpair setup.
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    pytest.fail('Unexpected asynchronous I/O in mocked publisher test')


def discover(monkeypatch, metadata, dependency=None, *, consent=True, status=200, headers=None, authorize=None):
    events = []
    monkeypatch.setattr(publisher, 'validated_address', lambda *args: ('pypi.org', 443, '8.8.8.8'))

    async def allowed():
        events.append('authorize')
        if authorize:
            await authorize()

    def request(url, address):
        events.append(url)
        body = metadata if isinstance(metadata, bytes) else json.dumps(metadata).encode()
        return status, headers or {'Content-Type': 'application/json'}, body

    result = run(publisher.discover_publisher(
        dependency or {'technology': 'example', 'ecosystem': 'python', 'docs_target': '1.2.3'},
        consent=consent, authorize=allowed, request=request))
    return result, events


def test_pypi_links_are_untrusted_bounded_candidates(monkeypatch):
    rows, events = discover(monkeypatch, {'info': {'name': 'Example', 'version': '1.2.3',
        'project_urls': {'Documentation': 'https://example.org/docs/1.2/'},
        'home_page': 'https://example.org/'}})
    assert events == ['authorize', 'authorize', 'https://pypi.org/pypi/example/1.2.3/json']
    assert rows[0]['source_url'] == 'https://example.org/docs/1.2/'
    assert rows[0]['path_prefix'] == '/docs/1.2/'
    assert rows[0]['publisher_link_field'] == 'info.project_urls.Documentation'
    assert rows[0]['registry_url'] == events[2]
    assert rows[0]['dependency_version'] == '1.2.3'
    assert 'coverage' not in rows[0]


def test_scoped_npm_uses_only_known_registry(monkeypatch):
    rows, events = discover(monkeypatch, {'name': '@owner/pkg', 'version': '1.2.3',
        'homepage': 'https://example.org/docs/'},
        {'technology': '@owner/pkg', 'ecosystem': 'javascript', 'docs_target': '1.2.3'})
    assert events == ['authorize', 'authorize', 'https://registry.npmjs.org/@owner/pkg/1.2.3']
    assert rows[0]['ecosystem'] == 'javascript'


def test_scoped_npm_endpoint_passes_production_url_validation():
    from docweave.integrations.public_sources import validated_address
    _, _, _, origin, url = publisher._identity(
        {'technology': '@owner/pkg', 'ecosystem': 'javascript', 'docs_target': '1.2.3'})
    def resolver(*args, **kwargs):
        return [(2, 1, 6, '', ('8.8.8.8', 443))]
    assert validated_address(url, {'origin': origin, 'path_prefix': '/'}, resolver=resolver)[0] == 'registry.npmjs.org'


@pytest.mark.parametrize('patch', [
    {'technology': 'https://private.example/pkg'}, {'technology': 'example?secret=x'},
    {'technology': '../example'}, {'docs_target': 'latest'}, {'docs_target': '^1.2.3'},
    {'docs_target': '1.2.3/private'}, {'ecosystem': 'unknown'},
])
def test_invalid_identity_never_calls_network(monkeypatch, patch):
    monkeypatch.setattr(publisher, 'validated_address', lambda *a: pytest.fail('DNS leak'))
    dep = {'technology': 'example', 'ecosystem': 'python', 'docs_target': '1.2.3', **patch}
    with pytest.raises(ValueError, match='Invalid publisher lookup identity'):
        run(publisher.discover_publisher(dep, consent=True, authorize=None))


@pytest.mark.parametrize('consent', [False, None, 1, 'true'])
def test_explicit_consent_required(monkeypatch, consent):
    monkeypatch.setattr(publisher, 'validated_address', lambda *a: pytest.fail('DNS leak'))
    with pytest.raises(ValueError, match='consent'):
        discover(monkeypatch, {}, consent=consent)


def test_authorization_denial_stops_request(monkeypatch):
    async def deny():
        raise PermissionError('revoked')
    with pytest.raises(PermissionError):
        discover(monkeypatch, {}, authorize=deny)


@pytest.mark.parametrize('body', [b'{"info":{},"info":{}}', b'[]', b'null', b'{' , b' ' * (2 * 1024 * 1024 + 1),
    b'{"info":{"name":"other","version":"1.2.3"}}',
    b'{"info":{"name":"example","version":"1.2.4"}}'])
def test_invalid_metadata_fails_safely(monkeypatch, body):
    with pytest.raises(ValueError, match='Publisher metadata unavailable'):
        discover(monkeypatch, body)


@pytest.mark.parametrize('status', [301, 302, 307, 404, 429, 500])
def test_no_redirect_or_retry(monkeypatch, status):
    with pytest.raises(ValueError, match='Publisher metadata unavailable'):
        discover(monkeypatch, {}, status=status, headers={'Location': 'https://private.local/'})


def test_hostile_links_are_not_candidates(monkeypatch):
    urls = ['http://example.org/docs/', 'https://user:pass@example.org/', 'https://127.0.0.1/',
        'https://example.local/', 'https://example.org/docs/?token=secret',
        'https://example.org/%2e%2e/', 'https://example.org/a/../b/', 'https://127.1/', 'https://github.com/',
        'https://github.com/owner/', 'https://owner.github.io/', 'https://example.org/docs/#section']
    rows, _ = discover(monkeypatch, {'info': {'name': 'example', 'version': '1.2.3',
        'project_urls': {f'Documentation {i}': value for i, value in enumerate(urls)}}})
    assert rows == []


def test_only_docs_homepage_fields_and_eight_unique_links(monkeypatch):
    rows, _ = discover(monkeypatch, {'info': {'name': 'example', 'version': '1.2.3',
        'project_urls': {**{f'Documentation {i}': f'https://example.org/docs/{i}/' for i in range(12)},
            'Source': 'https://example.org/source/'}, 'home_page': 'https://example.org/docs/0/'}})
    assert len(rows) == 8
    assert all('/docs/' in row['source_url'] for row in rows)


def test_shared_host_grant_stays_with_repo(monkeypatch):
    rows, _ = discover(monkeypatch, {'info': {'name': 'example', 'version': '1.2.3',
        'home_page': 'https://github.com/owner/example'}})
    assert rows[0]['source_url'] == 'https://github.com/owner/example'
    assert rows[0]['path_prefix'] == '/owner/example'


@pytest.mark.parametrize('url,path', [('https://example.org/guide', '/guide'),
    ('https://example.org/guide.html', '/guide.html'), ('https://example.org', '/')])
def test_exact_publisher_url_is_preserved(monkeypatch, url, path):
    rows, _ = discover(monkeypatch, {'info': {'name': 'example', 'version': '1.2.3', 'home_page': url}})
    assert rows[0]['source_url'] == url
    assert rows[0]['path_prefix'] == path


@pytest.mark.parametrize('headers', [{'Content-Type': 'text/html'},
    {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}])
def test_unsupported_metadata_representation(monkeypatch, headers):
    with pytest.raises(ValueError, match='Publisher metadata unavailable'):
        discover(monkeypatch, {}, headers=headers)


def test_request_failure_has_no_retry_and_no_leaked_error(monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, 'validated_address', lambda *a: ('pypi.org', 443, '8.8.8.8'))

    async def authorize():
        calls.append('authorize')

    def request(url, address):
        calls.append(url)
        raise OSError('private-marker')

    with pytest.raises(ValueError, match='^Publisher metadata unavailable$'):
        run(publisher.discover_publisher({'technology': 'example', 'ecosystem': 'python', 'docs_target': '1.2.3'},
            consent=True, authorize=authorize, request=request))
    assert calls == ['authorize', 'authorize', 'https://pypi.org/pypi/example/1.2.3/json']


@pytest.mark.parametrize('error', [PermissionError('revoked'), ValueError('context changed'), DomainError('context_changed')])
def test_authorization_rechecked_after_dns_before_request(monkeypatch, error):
    calls = []

    def resolve(*args):
        calls.append('dns')
        return 'pypi.org', 443, '8.8.8.8'

    async def authorize():
        calls.append('authorize')
        if calls.count('authorize') == 2:
            raise error

    def request(*args):
        pytest.fail('HTTP request after access was revoked during DNS')

    monkeypatch.setattr(publisher, 'validated_address', resolve)
    with pytest.raises(type(error)) as denied:
        run(publisher.discover_publisher({'technology': 'example', 'ecosystem': 'python', 'docs_target': '1.2.3'},
            consent=True, authorize=authorize, request=request))
    assert denied.value is error
    assert calls == ['authorize', 'dns', 'authorize']
