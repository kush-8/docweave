"""Bounded operator review manifests; project APIs cannot publish public sources."""
import hashlib
import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from docweave.schemas.common import StrictInput, Nonblank
from docweave.core.guardrails import assess_text


class Coverage(StrictInput):
    granularity: Literal['exact', 'major', 'minor']
    version: Nonblank = Field(max_length=100)


class CatalogEntry(StrictInput):
    technology: Nonblank = Field(max_length=200)
    ecosystem: Literal['python', 'javascript']
    docs_target: Nonblank = Field(max_length=100)
    coverage: Coverage
    package_aliases: list[Nonblank] = Field(default_factory=list, max_length=50)
    origin: Nonblank = Field(max_length=300)
    path_prefix: Nonblank = Field(max_length=1000)
    source_url: Nonblank = Field(max_length=2000)
    attribution: Nonblank = Field(max_length=4000)
    source_hash: str = Field(pattern='^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def bounded_public_scope(self):
        source = urlsplit(self.source_url)
        if (source.scheme != 'https' or source.port not in (None, 443) or not source.hostname
            or source.username is not None or source.password is not None or source.query or source.fragment
            or self.origin != f'https://{source.hostname}' or not self.path_prefix.startswith('/')
            or not self.path_prefix.endswith('/') or not source.path.startswith(self.path_prefix)
            or any(c in self.source_url + self.path_prefix for c in ('%', '\\'))
            or any(ord(c) < 32 for c in self.source_url + self.path_prefix)
            or any(part in ('.', '..') for part in (source.path + '/' + self.path_prefix).split('/'))
            or '//' in source.path or '//' in self.path_prefix or '.' not in source.hostname
            or source.hostname.endswith(('.local', '.localhost', '.internal'))):
            raise ValueError('Invalid public source scope')
        try:
            address = ipaddress.ip_address(source.hostname)
        except ValueError:
            pass
        else:
            if not address.is_global or address.is_reserved or address.is_multicast:
                raise ValueError('Invalid public source address')
        from docweave.services.catalog import _coverage_matches
        if not _coverage_matches(self.docs_target, self.coverage.model_dump()):
            raise ValueError('Documentation target and actual coverage disagree')
        if any(len(alias) > 200 for alias in self.package_aliases):
            raise ValueError('Invalid package alias')
        if assess_text(json.dumps(self.model_dump())).credential_blocked:
            raise ValueError('Public catalog metadata contains credentials')
        return self


class CatalogManifest(StrictInput):
    entries: list[CatalogEntry] = Field(min_length=1, max_length=100)


def parse_manifest(data):
    entries = CatalogManifest.model_validate(data).model_dump()['entries']
    identities = [(row['ecosystem'], row['technology'], row['docs_target'], row['source_url']) for row in entries]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate catalog entries')
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return entries, digest
