"""Short-lived publisher proposals; only an explicit owner decision approves private use."""
import json
from cryptography.fernet import Fernet, InvalidToken
from docweave.services.catalog_review import CatalogEntry


def seal_candidate(key, actor, project, dependency, candidate):
    payload = {'purpose': 'private-source-review:v1', 'actor': str(actor), 'project': project['id'],
        'revision': project['context_revision'], 'dependency': dependency['id'],
        'target': dependency.get('docs_target'), 'candidate': candidate}
    return Fernet(key).encrypt(json.dumps(payload, separators=(',', ':')).encode()).decode()


def open_candidate(key, token, actor, project, dependency):
    try:
        raw = token.encode()
        if len(raw) > 16384 or raw != raw.strip():
            raise ValueError
        # Fernet's base64 decoder accepts trailing bytes; canonical encoding is required.
        import base64
        if base64.urlsafe_b64encode(base64.urlsafe_b64decode(raw)) != raw:
            raise ValueError
        data = json.loads(Fernet(key).decrypt(raw, ttl=600))
        target = next(item.get('docs_target') for item in project['stack'] if item['id'] == dependency)
        if (data.get('purpose'), data.get('actor'), data.get('project'), data.get('revision'), data.get('dependency'), data.get('target')) != (
            'private-source-review:v1', str(actor), project['id'], project['context_revision'], dependency, target):
            raise ValueError
        return data['candidate']
    except (InvalidToken, ValueError, KeyError, TypeError, StopIteration):
        raise ValueError('Source proposal expired or project context changed; discover again') from None


def review_values(dependency, candidate, coverage, accept_fallback):
    if coverage.get('granularity') != 'exact' and accept_fallback is not True:
        raise ValueError('Explicit version fallback acceptance is required')
    validated = CatalogEntry.model_validate({
        'technology': dependency['technology'], 'ecosystem': dependency['ecosystem'],
        'docs_target': dependency['docs_target'], 'coverage': coverage, 'source_hash': '0' * 64,
        **{key: candidate[key] for key in ('source_url', 'origin', 'path_prefix', 'attribution')},
    }).model_dump()
    return {**{key: validated[key] for key in ('technology', 'docs_target', 'coverage', 'source_url', 'origin', 'path_prefix', 'attribution')},
        'accept_fallback': accept_fallback}
