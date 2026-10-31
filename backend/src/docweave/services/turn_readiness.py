"""Pure turn gating; retrieval confidence alone never establishes a source wait."""


def decide_turn_readiness(required_dependency_ids: list[str] | None, dependency_states: dict[str, dict]) -> dict:
    if required_dependency_ids is None:
        return {'status': 'clarify', 'dependency_ids': [], 'reason': 'dependency requirements are uncertain'}
    required = sorted(set(required_dependency_ids))
    if any(dependency_id not in dependency_states for dependency_id in required):
        return {'status': 'clarify', 'dependency_ids': required, 'reason': 'dependency is absent from current project context'}
    unresolved = [dependency_id for dependency_id in required if dependency_states[dependency_id].get('status') != 'ready']
    if not unresolved:
        return {'status': 'ready', 'dependency_ids': required, 'reason': 'all required sources are ready'}
    for status in ('pending_review', 'consent_required', 'capacity', 'failed'):
        blocked = [dependency_id for dependency_id in unresolved if dependency_states[dependency_id].get('status') == status]
        if blocked:
            return {'status': status, 'dependency_ids': blocked, 'reason': 'required sources need action'}
    if all(dependency_states[dependency_id].get('status') == 'waiting_for_sources' and dependency_states[dependency_id].get('active_job') is True for dependency_id in unresolved):
        return {'status': 'waiting_for_sources', 'dependency_ids': unresolved, 'reason': 'required sources have active processing jobs'}
    return {'status': 'abstain', 'dependency_ids': unresolved, 'reason': 'required documentation is unavailable without active processing'}
