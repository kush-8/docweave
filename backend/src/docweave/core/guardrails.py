"""Deterministic leaf checks, not comprehensive secret or injection detection.

These helpers do not authorize processing or persist quarantine/review state.
Callers must enforce current ownership, source eligibility and nonwaivable blocks.
"""

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata

RULE_REVISION = 'deterministic-v1'
MAX_SCAN_CHARS = 2_000_000
_PLACEHOLDER = re.compile(r'^(?:YOUR[_-]?[A-Z_]+|EXAMPLE[_-]?[A-Z_]*|REPLACE[_-]?ME|<[^>]+>|\$\{[^}]+\}|password|changeme|x{3,}|\*+)$', re.I)
_CREDENTIAL_RULES = (
    ('private-key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')),
    ('github-token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})\b')),
    ('provider-token', re.compile(r'\b(?:gsk_[A-Za-z0-9]{40,255}|sk-proj-[A-Za-z0-9_-]{40,255}|xox[baprs]-[A-Za-z0-9-]{20,255})\b')),
    ('aws-access-key', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('google-api-key', re.compile(r'\bAIza[A-Za-z0-9_-]{35}\b')),
    ('authorization', re.compile(r'\bauthorization\s*:\s*(?:bearer|basic)\s+(?P<value>[^\s"\']{8,4096})', re.I)),
    ('credential-uri', re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s/:@]+:(?P<value>[^\s/@]{3,4096})@', re.I)),
)
_INJECTION_RULES = (
    ('instruction-override', re.compile(r'\b(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions?|rules?|messages?)\b', re.I)),
    ('role-spoof', re.compile(r'<\|(?:im_start|start_header_id)\|>\s*(?:system|developer)|\[INST\]|<\s*(?:system|developer)\s*>', re.I)),
    ('prompt-exposure', re.compile(r'\b(?:reveal|expose|print|show)\s+(?:the\s+)?(?:system|developer|hidden)\s+prompt\b', re.I)),
)


@dataclass(frozen=True)
class Assessment:
    document_version: str
    content_hash: str
    parser_config_hash: str
    rule_revision: str
    findings: tuple[str, ...]
    credential_blocked: bool
    injection_flagged: bool
    complete: bool


def _config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def assess_text(text: str, *, document_version: str = '', parser_config: dict | None = None) -> Assessment:
    """Return rule IDs only; never retain a matching credential in findings."""
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    config_hash = _config_hash(parser_config or {})
    complete = len(text) <= MAX_SCAN_CHARS
    normalized = unicodedata.normalize('NFKC', text[:MAX_SCAN_CHARS])
    normalized = ''.join(character for character in normalized if unicodedata.category(character) != 'Cf')
    credentials = tuple(rule for rule, pattern in _CREDENTIAL_RULES if any(
        'value' not in match.groupdict() or not _PLACEHOLDER.fullmatch(match['value'])
        for match in pattern.finditer(normalized)
    ))
    injections = tuple(rule for rule, pattern in _INJECTION_RULES if pattern.search(normalized))
    findings = credentials + injections + (() if complete else ('scan-bound-exceeded',))
    return Assessment(document_version, content_hash, config_hash, RULE_REVISION, findings, bool(credentials), bool(injections), complete)


def assessment_is_current(assessment: Assessment, text: str, *, document_version: str, parser_config: dict) -> bool:
    """Freshness only: a current assessment may still block or require review."""
    return (
        assessment.complete
        and assessment.rule_revision == RULE_REVISION
        and assessment.document_version == document_version
        and assessment.content_hash == hashlib.sha256(text.encode()).hexdigest()
        and assessment.parser_config_hash == _config_hash(parser_config)
    )


def validate_evidence_claims(claims: list[dict], evidence: dict[str, dict]) -> None:
    """Require exact offsets/quotes in caller-supplied currently authorized evidence.

    This establishes structural membership, not semantic entailment or authority.
    Callers must reauthorize evidence before passing it here and before release.
    """
    if not isinstance(claims, list) or len(claims) > 1000:
        raise ValueError('invalid evidence claims')
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('evidence_id'), str):
            raise ValueError('invalid evidence claim')
        supplied = evidence.get(claim['evidence_id'])
        start, end = claim.get('start'), claim.get('end')
        if (
            not supplied
            or not isinstance(supplied.get('text'), str)
            or not isinstance(claim.get('version'), str)
            or claim['version'] != supplied.get('version')
            or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(supplied['text'])
            or not isinstance(claim.get('quote'), str)
            or claim['quote'] != supplied['text'][start:end]
        ):
            raise ValueError('evidence claim does not match supplied span')
