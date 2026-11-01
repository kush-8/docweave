"""Pure public-catalog matching. Authority and project selections come from callers."""

import re

from docweave.integrations.stack import Dependency


def _canonical(name: str, ecosystem: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower() if ecosystem == 'python' else name.lower()


def _coverage_matches(target: str, coverage: dict) -> bool:
    version, granularity = coverage.get('version'), coverage.get('granularity')
    if not isinstance(version, str):
        return False
    if granularity == 'exact':
        return version == target
    parts = 1 if granularity == 'major' else 2 if granularity == 'minor' else 0
    if not parts or not re.fullmatch(r'\d+(?:\.\d+){0,3}(?:[-+][A-Za-z0-9.-]+)?', target):
        return False
    return bool(re.fullmatch(r'\d+' + r'\.\d+' * (parts - 1), version)) and target.split('.')[:parts] == version.split('.')


def match_documentation(
    dependency: Dependency,
    entries: list[dict],
    ready_generation_id: str,
    *,
    accepted_fallback_revision_ids=(),
) -> dict:
    """Match actual version coverage, then current atomic index publication.

    Only explicit catalog package_aliases map package names to technologies.
    Fallback acceptance is a per-project input, never a public-entry flag.
    This function neither fetches unknown packages nor authorizes publication.
    """
    target = dependency.documentation_target
    if not isinstance(target, str) or not target:
        return {'status': 'pending_review', 'entry': None, 'reason': 'unknown documentation version'}
    name = _canonical(dependency.name, dependency.ecosystem)
    matches = []
    accepted = set(accepted_fallback_revision_ids)
    for entry in entries:
        if entry.get('ecosystem') != dependency.ecosystem or entry.get('eligible') is not True:
            continue
        aliases = entry.get('package_aliases', [])
        if not isinstance(aliases, list):
            continue
        names = [entry.get('technology'), *aliases]
        if not any(isinstance(candidate, str) and _canonical(candidate, dependency.ecosystem) == name for candidate in names):
            continue
        coverage = entry.get('coverage')
        if not isinstance(coverage, dict) or not _coverage_matches(target, coverage):
            continue
        exact = coverage.get('granularity') == 'exact'
        if not entry.get('revision_id') or not isinstance(entry.get('docs_target'), str) or not entry['docs_target']:
            status, reason = 'pending_review', 'incomplete catalog provenance'
        elif entry.get('source_approved') is not True:
            status, reason = 'pending_review', 'source approval required'
        elif not exact and entry['revision_id'] not in accepted:
            status, reason = 'pending_review', 'version fallback approval required'
        elif entry.get('status') == 'blocked_policy':
            status, reason = 'pending_review', 'source or processing approval required'
        elif entry.get('status') == 'completion_unknown':
            status, reason = 'failed', 'provider result uncertain; operator reconciliation required'
        elif entry.get('status') in ('failed', 'consent_required', 'capacity', 'pending_review'):
            status, reason = entry['status'], 'documentation requires action'
        elif (
            not ready_generation_id
            or entry.get('generation_id') != ready_generation_id
            or entry.get('indexed_generation_id') != ready_generation_id
            or entry.get('status') != 'indexed'
        ):
            status, reason = ('waiting_for_sources', 'current generation is not atomically indexed') if entry.get('active_job') is True else ('missing', 'no active indexing work')
        else:
            status, reason = 'ready', 'matching eligible indexed coverage'
        matches.append((not exact, {'ready': 0, 'waiting_for_sources': 1, 'pending_review': 2, 'consent_required': 3, 'capacity': 4, 'failed': 5, 'missing': 6}[status], str(entry.get('revision_id', '')), {'status': status, 'entry': entry, 'reason': reason}))
    if not matches:
        return {'status': 'missing', 'entry': None, 'reason': 'no eligible matching version coverage'}
    return min(matches, key=lambda match: match[:3])[3]


def documentation_coverage(project, entries, generation):
    """One current selection per dependency; acceptance never crosses a target change."""
    selections = {item['dependency_id']: item for item in project.get('catalog_selections', [])}
    result = []
    for item in project['stack']:
        dependency = Dependency(item.get('ecosystem', ''), item['technology'], documentation_target=item.get('docs_target'))
        selection = selections.get(item['id'])
        private = next((entry for entry in entries if entry.get('private_selection') and entry.get('dependency_id') == item['id']), None)
        if private:
            selection = {'revision_id': private['revision_id'], 'fallback_accepted': True, 'accepted_docs_target': private['accepted_docs_target']}
        accepted = [selection['revision_id']] if selection and selection.get('fallback_accepted') and selection.get('accepted_docs_target') == item.get('docs_target') else []
        candidates = [match_documentation(dependency, [entry], generation, accepted_fallback_revision_ids=accepted) for entry in entries]
        candidates = [candidate for candidate in candidates if candidate['entry']]
        chosen = next((candidate for candidate in candidates if selection and candidate['entry']['revision_id'] == selection['revision_id']), None)
        match = chosen or match_documentation(dependency, entries, generation, accepted_fallback_revision_ids=accepted)
        if not private and item['id'] in project.get('excluded_documentation', []):
            match = {'status': 'missing', 'entry': None, 'reason': 'documentation selection removed'}
        result.append({'dependency_id': item['id'], 'technology': item['technology'], 'docs_target': item.get('docs_target'),
            **match, 'selected_revision_id': selection['revision_id'] if chosen else None, 'candidates': candidates})
    return result
