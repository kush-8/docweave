from uuid import UUID
import pytest
from docweave.integrations.stack import parse_stack
from docweave.services.project_memory import update_memory

PROJECT = UUID(int=42)
SHA = "a" * 40

def test_stack_update_preserves_dependency_identity_and_revision_on_noop():
    scan = parse_stack({"package.json": b'{"dependencies":{"react":"19.0.0"}}'})
    first = update_memory(PROJECT, [], None, 1, scan, SHA)
    assert first["context_revision"] == 2
    assert first["last_commit_sha"] == SHA
    second = update_memory(PROJECT, first["stack"], first["stack_fingerprint"], 2, scan, "b"*40)
    assert second["context_revision"] == 2
    assert second["stack"][0]["id"] == first["stack"][0]["id"]
    assert second["last_commit_sha"] == "b"*40

def test_version_change_keeps_dependency_id_but_invalidates_context():
    a = parse_stack({"package.json": b'{"dependencies":{"react":"19.0.0"}}'})
    b = parse_stack({"package.json": b'{"dependencies":{"react":"19.1.0"}}'})
    old = update_memory(PROJECT, [], None, 1, a, SHA)
    new = update_memory(PROJECT, old["stack"], old["stack_fingerprint"], 2, b, "b"*40)
    assert new["context_revision"] == 3
    assert new["stack"][0]["id"] == old["stack"][0]["id"]


def test_incomplete_scan_cannot_overwrite_good_memory():
    bad = parse_stack({"package.json": b'{broken'})
    with pytest.raises(ValueError, match="incomplete"):
        update_memory(PROJECT, [], None, 1, bad, SHA)


def test_same_package_in_multiple_roles_has_distinct_stable_dependency_ids():
    scan=parse_stack({'package.json': b'{"dependencies":{"react":"19"},"devDependencies":{"react":"19"}}'})
    memory=update_memory(PROJECT, [], None, 1, scan, SHA)
    assert len({entry['id'] for entry in memory['stack']}) == len(memory['stack']) == 2
