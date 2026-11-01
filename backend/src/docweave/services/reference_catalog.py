"""Explicit bounded reference coverage; never infer package-version compatibility."""
import json
from docweave.core.paths import ROOT


def reference_catalog():
    registry=json.loads((ROOT/'backend/catalog/required-sources.json').read_text(encoding='utf-8'))
    return {'items':registry['entries'],'publication_state':registry['publication_state'],
        'coverage_policy':registry['coverage_policy'],'next_cursor':None}
