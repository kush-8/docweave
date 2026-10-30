"""One approved public text page; every redirect and resolved address stays bounded."""

import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

MAX_RESPONSE = 2 * 1024 * 1024
AGENT = "DocWeave/0.1"


def validated_address(url, selection, *, resolver=None, robots=False):
    resolver = resolver or socket.getaddrinfo
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
        origin = f"{parsed.scheme}://{parsed.hostname}"
        if port != 443 or parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if origin != selection["origin"] or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError
        path = unquote(parsed.path)
        if "%" in path or "\\" in path or any(ord(c) < 32 for c in url) or "//" in path or any(p in (".", "..") for p in path.split("/")):
            raise ValueError
        if path != parsed.path:
            raise ValueError
        if robots and path != "/robots.txt":
            raise ValueError
        if not robots and not path.startswith(selection["path_prefix"]):
            raise ValueError
        addresses = resolver(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global or ip.is_reserved or ip.is_multicast:
                raise ValueError
        return parsed.hostname, port, addresses[0][4][0]
    except (TypeError, AttributeError, IndexError):
        raise ValueError("Unsafe source URL") from None


def _request(url, address):
    host, port, ip = address
    time.sleep(1)  # The global ingestion lock plus a pre-request delay enforces <=1 request/second/host.
    deadline = time.monotonic() + 10
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(host, port, timeout=10, context=context)
    try:
        raw = socket.create_connection((ip, port), timeout=10)
        try:
            connection.sock = context.wrap_socket(raw, server_hostname=host)
        except BaseException:
            raw.close()
            raise
        if ipaddress.ip_address(connection.sock.getpeername()[0]) != ipaddress.ip_address(ip):
            raise ValueError("Unexpected peer")
        connection.sock.settimeout(max(0.01, deadline - time.monotonic()))
        connection.request("GET", urlsplit(url).path, headers={"User-Agent": AGENT, "Accept-Encoding": "identity", "Accept": "text/plain, text/markdown"})
        response = connection.getresponse()
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("Compressed source is unsupported")
        chunks, length = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Source deadline")
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_RESPONSE + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            if length > MAX_RESPONSE:
                raise ValueError("Source too large")
        return response.status, dict(response.getheaders()), b"".join(chunks)
    except (http.client.HTTPException, ssl.SSLError) as error:
        raise OSError("Source unavailable") from error
    finally:
        connection.close()


async def fetch_document(selection, *, authorize=None):
    async def get(url, robots=False):
        address = await asyncio.to_thread(validated_address, url, selection, robots=robots)
        if authorize:
            await authorize()
        status, headers, content = await asyncio.to_thread(_request, url, address)
        return status, {key.lower(): value for key, value in headers.items()}, content

    robots_url = selection["origin"] + "/robots.txt"
    status, _, body = await get(robots_url, robots=True)
    robots = RobotFileParser()
    if status == 404:
        robots.parse([])
    elif status == 200:
        robots.parse(body.decode("utf-8-sig").splitlines())
    elif status >= 500 or status == 429:
        raise OSError("Robots temporarily unavailable")
    else:
        raise ValueError("Robots permission unavailable")
    url = selection["source_url"]
    for attempt in range(4):
        if not robots.can_fetch(AGENT, url):
            raise ValueError("Robots disallows source")
        delay = robots.crawl_delay(AGENT) or 1
        if delay > 10:
            raise ValueError("Source crawl delay exceeds worker bound")
        if delay > 1:
            await asyncio.sleep(delay - 1)
        status, headers, body = await get(url)
        if status in (301, 302, 303, 307, 308):
            target = urljoin(url, headers.get("location", ""))
            await asyncio.to_thread(validated_address, target, selection)
            url = target
            continue
        if status >= 500 or status == 429:
            raise OSError("Source temporarily unavailable")
        if status != 200:
            raise ValueError("Source unavailable")
        media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media not in ("text/plain", "text/markdown"):
            raise ValueError("Only public TXT/Markdown pages are supported")
        if not selection["attribution"].strip():
            raise ValueError("Source attribution is required")
        return body, "text/markdown" if urlsplit(url).path.endswith((".md", ".markdown")) else media
    raise ValueError("Redirect limit exceeded")
