"""Bounded UTF-8 decoding and normalization for the isolated parser."""

import hashlib
from html.parser import HTMLParser
import re
import unicodedata
from docweave.rag.contracts import CONFIGURATION, MAX_BYTES, MAX_CHARS
from docweave.rag.chunking import chunk_text


MAX_HTML_NODES = 100_000
MAX_HTML_DEPTH = 64
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
_DROP = {'head', 'title', 'script', 'style', 'nav', 'aside', 'header', 'footer', 'form', 'template', 'svg', 'math', 'iframe',
    'object', 'embed', 'canvas', 'noscript', 'button', 'select', 'textarea', 'dialog', 'audio', 'video'}
_BLOCK = {'p', 'div', 'section', 'article', 'main', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'pre', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'tr', 'blockquote', 'br', 'hr'}
_OPTIONAL = {'p', 'li', 'dt', 'dd', 'tr', 'td', 'th', 'thead', 'tbody', 'tfoot', 'html', 'body'}


class _DocumentationHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.buffers = {'body': [], 'main': [], 'article': []}
        self.scopes = set()
        self.nodes = self.characters = 0

    def _node(self):
        self.nodes += 1
        if self.nodes > MAX_HTML_NODES:
            raise ValueError('HTML node limit exceeded')

    def _emit(self, value):
        if self.stack and self.stack[-1][1]:
            return
        self.characters += len(value)
        if self.characters > MAX_CHARS:
            raise ValueError('HTML text limit exceeded')
        self.buffers['body'].append(value)
        for scope in ('main', 'article'):
            if any(tag == scope for tag, _ in self.stack):
                self.buffers[scope].append(value)

    def handle_starttag(self, tag, attrs):
        self._node()
        # HTML permits these common implicit closing tags; other broken nesting fails closed.
        if self.stack and (self.stack[-1][0] == tag and tag in ('li', 'dt', 'dd', 'p', 'tr', 'td', 'th')
            or self.stack[-1][0] == 'p' and tag in _BLOCK - {'br', 'hr'}):
            self.handle_endtag(self.stack[-1][0])
        attrs = dict(attrs)
        style = re.sub(r'\s+', '', attrs.get('style') or '').lower()
        hidden = ('hidden' in attrs or 'inert' in attrs or (attrs.get('aria-hidden') or '').lower() == 'true'
            or re.search(r'(?:^|;)(?:display:none|visibility:(?:hidden|collapse)|opacity:0)(?:!important)?(?:;|$)', style))
        chrome = (attrs.get('role') or '').lower() in ('navigation', 'banner', 'contentinfo', 'complementary', 'search')
        dropped = bool(tag in _DROP or hidden or chrome or self.stack and self.stack[-1][1])
        if tag in _BLOCK and not dropped:
            self._emit('\n')
        if tag not in _VOID:
            self.stack.append((tag, dropped))
            if len(self.stack) > MAX_HTML_DEPTH:
                raise ValueError('HTML depth limit exceeded')
            if tag in ('main', 'article') and not dropped:
                self.scopes.add(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        self._node()
        if tag in _VOID:
            return
        tags = [item[0] for item in self.stack]
        if tag not in tags:
            if tag in _OPTIONAL or self.stack and self.stack[-1][1]:
                return
            raise ValueError('Malformed HTML nesting')
        index = len(tags) - 1 - tags[::-1].index(tag)
        # Dropped chrome cannot contribute text; explicit documentation boundaries may close flow wrappers.
        allowed = _OPTIONAL | ({'div', 'section'} if tag in ('main', 'article', 'body', 'html') else set())
        if any(open_tag not in allowed and not dropped for open_tag, dropped in self.stack[index + 1:]):
            raise ValueError('Malformed HTML nesting')
        if tag in _BLOCK:
            self._emit('\n')
        del self.stack[index:]

    def handle_data(self, data):
        self._node()
        if self.stack and self.stack[-1][1]:
            return
        data = ''.join(c for c in data if unicodedata.category(c) != 'Cf')
        if '\ufffd' in data:
            raise ValueError('Invalid HTML character reference')
        if not any(tag == 'pre' for tag, _ in self.stack):
            data = re.sub(r'\s+', ' ', data)
        self._emit(data)

    def handle_comment(self, data):
        self._node()

    def unknown_decl(self, data):
        raise ValueError('Unsupported HTML declaration')

    def text(self):
        if self.rawdata.strip():
            raise ValueError('Incomplete HTML')
        self.close()
        if self.rawdata.strip() or any(tag not in _OPTIONAL for tag, _ in self.stack):
            raise ValueError('Incomplete HTML')
        scope = 'main' if 'main' in self.scopes else 'article' if 'article' in self.scopes else 'body'
        result = ''.join(self.buffers[scope])
        return re.sub(r'\n[ \t]*\n+', '\n', re.sub(r'[ \t]+\n', '\n', result)).strip()


def parse_text(content: bytes, media_type: str) -> dict:
    if media_type not in ("text/plain", "text/markdown", "text/html") or len(content) > MAX_BYTES:
        raise ValueError("Unsupported or oversized text")
    normalized = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if any((ord(c) < 32 or media_type == 'text/html' and unicodedata.category(c) == 'Cc') and c not in "\n\t" for c in normalized):
        raise ValueError("Invalid text")
    if media_type == 'text/html':
        parser = _DocumentationHTML()
        parser.feed(normalized)
        normalized = parser.text()
    if len(normalized) > MAX_CHARS or not normalized.strip():
        raise ValueError("Invalid text")
    chunks = chunk_text(normalized, media_type)
    return {"text": normalized, "sha256": hashlib.sha256(normalized.encode()).hexdigest(), "chunks": chunks,
        "configuration": CONFIGURATION + ":" + media_type}
