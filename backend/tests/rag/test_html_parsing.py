import hashlib
import json
import subprocess
import sys

import pytest

from docweave.rag import parsing
from tests.paths import BACKEND_ROOT


def test_main_docs_preserve_headings_code_lists_and_offsets():
    raw = b'''<!doctype html><html><head><title>Chrome</title></head><body>
    <header>Top</header><article>Other article</article><main><h1>Install &amp; use</h1>
    <p>Run <code>example()</code> now.</p><pre><code>if ready:\n    run()\n</code></pre>
    <ul><li>First</li><li>Second</li></ul></main><footer>Bottom</footer></body></html>'''
    result = parsing.parse_text(raw, 'text/html')
    assert 'Install & use' in result['text']
    assert 'Run example() now.' in result['text']
    assert 'if ready:\n    run()' in result['text']
    assert 'First\n' in result['text'] and 'Second' in result['text']
    assert all(word not in result['text'] for word in ('Chrome', 'Top', 'Other article', 'Bottom'))
    assert result['configuration'].endswith(':text/html')
    assert result['sha256'] == hashlib.sha256(result['text'].encode()).hexdigest()
    for chunk in result['chunks']:
        assert result['text'][chunk['start']:chunk['end']].strip()
        assert chunk['line_start'] == result['text'][:chunk['start']].count('\n') + 1
        assert chunk['line_end'] == result['text'][:chunk['end'] - 1].count('\n') + 1


def test_article_scope_then_body_fallback():
    result = parsing.parse_text(b'<body><p>Sidebar</p><article><h2>Docs</h2><p>Use this.</p></article></body>', 'text/html')
    assert result['text'] == 'Docs\nUse this.'
    assert parsing.parse_text(b'<body><nav>menu</nav><aside>sidebar</aside><div role="navigation">chrome</div><p>Visible</p></body>', 'text/html')['text'] == 'Visible'


@pytest.mark.parametrize('hidden', ['hidden', 'aria-hidden="true"', 'inert',
    'style="display: none"', 'style="visibility:hidden"', 'style="opacity:0"'])
def test_hidden_subtrees_and_executable_content_removed(hidden):
    raw = f'''<main><p>Visible\u200b docs</p><div {hidden}><p>secret-marker</p></div>
    <script>secret-marker</script><style>secret-marker</style><form>secret-marker</form>
    <svg><text>secret-marker</text></svg><template>secret-marker</template><!--secret-marker--></main>'''
    assert parsing.parse_text(raw.encode(), 'text/html')['text'] == 'Visible docs'


@pytest.mark.parametrize('raw', [b'<main><script>docs()</script></main>', b'<body><iframe src="https://docs.example/"></iframe></body>',
    b'<main><p>Unclosed', b'<main><p>Broken</div></main>', b'<main><p>text</p>',
    b'<main>\x00bad</main>', b'<main>&#0;</main>', b'<main>Docs</main><p'])
def test_empty_malformed_or_invisible_pages_rejected(raw):
    with pytest.raises(ValueError):
        parsing.parse_text(raw, 'text/html')


def test_html_resource_limits(monkeypatch):
    with pytest.raises(ValueError):
        parsing.parse_text(b'<main>' + b'<div>' * 65 + b'text' + b'</div>' * 65 + b'</main>', 'text/html')
    monkeypatch.setattr(parsing, 'MAX_HTML_NODES', 8)
    with pytest.raises(ValueError):
        parsing.parse_text(b'<main>' + b'<p>a</p>' * 4 + b'</main>', 'text/html')


def test_original_bytes_and_extracted_text_bounded(monkeypatch):
    monkeypatch.setattr(parsing, 'MAX_BYTES', 40)
    with pytest.raises(ValueError):
        parsing.parse_text(b'<main>' + b'x' * 40 + b'</main>', 'text/html')
    monkeypatch.setattr(parsing, 'MAX_CHARS', 4)
    with pytest.raises(ValueError):
        parsing.parse_text(b'<main>12345</main>', 'text/html')


def test_optional_html_end_tags_supported():
    assert parsing.parse_text(b'<main><ul><li>One<li>Two</ul></main>', 'text/html')['text'] == 'One\nTwo'


def test_inline_void_tags_do_not_implicitly_close_paragraphs():
    assert parsing.parse_text(b'<main><p>First<br>Second<br/><span>Third</span></p></main>', 'text/html')['text'] == 'First\nSecond\nThird'


def test_discarded_chrome_can_have_broken_foreign_markup_without_leaking():
    raw = b'<body><header><span><svg><path/></svg><rect>secret</g></svg></span></header><main>Docs</main></body>'
    assert parsing.parse_text(raw, 'text/html')['text'] == 'Docs'


def test_explicit_documentation_boundary_closes_only_flow_containers():
    assert parsing.parse_text(b'<main><div><p>Docs</p></main><nav>secret</nav>', 'text/html')['text'] == 'Docs'
    with pytest.raises(ValueError):
        parsing.parse_text(b'<main><pre>incomplete</main>', 'text/html')


def test_hydration_scripts_after_closed_document_do_not_add_content():
    raw = b'<html><body><main>Docs</main></body></html><script>secret()</script></body></html>'
    assert parsing.parse_text(raw, 'text/html')['text'] == 'Docs'


def test_html_runs_in_isolated_standard_library_parser(tmp_path):
    entry = BACKEND_ROOT / 'src' / 'docweave' / 'text_parser.py'
    raw = b'<main><h1>Docs</h1><pre>example()</pre></main>'
    result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'text/html'],
        input=raw, capture_output=True, timeout=10, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == parsing.parse_text(raw, 'text/html')


def test_public_fetch_keeps_original_html_bytes_and_media(monkeypatch):
    from docweave.integrations import public_sources

    raw = b'<main><h1>Docs</h1><p>Original &amp; raw.</p></main>'
    calls = []

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    def request(url, address):
        calls.append(url)
        if url.endswith('/robots.txt'):
            return 404, {}, b''
        return 200, {'Content-Type': 'text/html; charset=utf-8'}, raw

    monkeypatch.setattr(public_sources.asyncio, 'to_thread', inline)
    monkeypatch.setattr(public_sources, 'validated_address', lambda *a, **k: ('example.org', 443, '8.8.8.8'))
    monkeypatch.setattr(public_sources, '_request', request)
    task = public_sources.fetch_document({'origin': 'https://example.org', 'path_prefix': '/docs/',
        'source_url': 'https://example.org/docs/page.md', 'attribution': 'Example Docs'})
    try:
        task.send(None)
    except StopIteration as done:
        assert done.value == (raw, 'text/html')
    else:
        pytest.fail('Unexpected external I/O')
    finally:
        task.close()
    assert calls == ['https://example.org/robots.txt', 'https://example.org/docs/page.md']
