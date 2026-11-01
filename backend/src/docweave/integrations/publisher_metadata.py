"""Consent-gated registry metadata; publisher links remain untrusted review candidates."""

import asyncio
import ipaddress
import json
import re
from urllib.parse import urlsplit

from docweave.integrations.public_sources import MAX_RESPONSE, _request, validated_address


def _identity(dependency):
    ecosystem = dependency.get('ecosystem')
    name, version = dependency.get('technology'), dependency.get('docs_target')
    if not isinstance(name, str) or not isinstance(version, str) or len(name) > 214 or len(version) > 100:
        raise ValueError('Invalid publisher lookup identity')
    if ecosystem == 'python':
        valid_name = re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name)
        valid_version = re.fullmatch(
            r'(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?'
            r'(?:\.post[0-9]+)?(?:\.dev[0-9]+)?(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?', version)
        name = re.sub(r'[-_.]+', '-', name).lower()
        origin = 'https://pypi.org'
        path = f'/pypi/{name}/{version}/json'
    elif ecosystem == 'javascript':
        valid_name = re.fullmatch(r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*', name)
        valid_version = re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'
            r'(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', version)
        origin = 'https://registry.npmjs.org'
        path = f'/{name}/{version}'
    else:
        raise ValueError('Invalid publisher lookup identity')
    if not valid_name or not valid_version:
        raise ValueError('Invalid publisher lookup identity')
    return ecosystem, name, version, origin, origin + path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _candidate_scope(value):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme != 'https' or parsed.port not in (None, 443) or not host
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or any(c in value for c in ('%', '\\')) or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
            or '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid'))
            or '//' in parsed.path or any(part in ('.', '..') for part in parsed.path.split('/'))):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if re.fullmatch(r'[0-9.]+', host):
                return None
        else:
            if not address.is_global or address.is_reserved or address.is_multicast:
                return None
        path = parsed.path or '/'
        # A non-directory URL grants exactly that path; never guess a slash or parent directory.
        prefix = path
        parts = [part for part in prefix.split('/') if part]
        if host in ('github.com', 'gitlab.com', 'bitbucket.org') and len(parts) < 2:
            return None
        if (host in ('github.io', 'readthedocs.io', 'pages.dev', 'netlify.app', 'vercel.app')
            or (host.endswith('.github.io') and not parts)):
            return None
        origin = f'https://{host}'
        return value, origin, prefix
    except ValueError:
        return None


async def discover_publisher(dependency: dict, *, authorize, consent: bool, request=None) -> list[dict]:
    """Send only a validated identity to one registry, after caller consent and authorization.

    ``authorize`` is an async zero-argument callback. ``request`` is a synchronous
    injectable transport with the public_sources._request contract; production
    uses that bounded, pinned-IP transport without ambient cookies or credentials.
    Empty results mean valid metadata contained no safe documentation/homepage links.
    """
    if consent is not True:
        raise ValueError('Explicit publisher lookup consent is required')
    if not isinstance(dependency, dict):
        raise ValueError('Invalid publisher lookup identity')
    ecosystem, name, version, origin, registry_url = _identity(dependency)
    if not callable(authorize):
        raise ValueError('Publisher lookup authorization is required')
    await authorize()
    try:
        address = await asyncio.to_thread(validated_address, registry_url, {'origin': origin, 'path_prefix': '/'})
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ValueError('Publisher metadata unavailable') from None
    await authorize()
    try:
        status, headers, body = await asyncio.to_thread(request or _request, registry_url, address)
        headers = {key.lower(): value for key, value in headers.items()}
        if (status != 200 or not isinstance(body, bytes) or len(body) > MAX_RESPONSE
            or headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json'
            or headers.get('content-encoding', 'identity').lower() != 'identity'):
            raise ValueError
        data = json.loads(body, object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant)
        info = data['info'] if ecosystem == 'python' else data
        actual = _identity({'technology': info['name'], 'ecosystem': ecosystem, 'docs_target': info['version']})
        if actual[:3] != (ecosystem, name, version):
            raise ValueError
        links = []
        if ecosystem == 'python':
            project_urls = info.get('project_urls') or {}
            if not isinstance(project_urls, dict):
                raise ValueError
            for label, value in project_urls.items():
                if len(label) <= 100 and re.fullmatch(r'(?:documentation|docs|homepage|home page)(?: [0-9]+)?', label, re.I):
                    links.append((f'info.project_urls.{label}', value))
            links.extend((f'info.{field}', info.get(field)) for field in ('docs_url', 'home_page'))
        else:
            links.append(('homepage', info.get('homepage')))
        candidates, seen = [], set()
        for field, value in links:
            scope = _candidate_scope(value)
            if scope is None or scope[0] in seen:
                continue
            source_url, source_origin, prefix = scope
            seen.add(source_url)
            candidates.append({'source_url': source_url, 'origin': source_origin, 'path_prefix': prefix,
                'attribution': f'Publisher metadata for {name} {version} ({registry_url}); {field}',
                'registry_url': registry_url, 'dependency_name': name, 'dependency_version': version,
                'ecosystem': ecosystem, 'publisher_link_field': field})
            if len(candidates) == 8:
                break
        return candidates
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise ValueError('Publisher metadata unavailable') from None
