"""Ownership mapping must not silently assign shared legacy data."""
from uuid import UUID
import pytest
from docweave.services.ownership import ownership_mapping

A, B, P, Q = [UUID(int=i) for i in range(1, 5)]

def test_sole_owner_maps_without_changing_project_ids():
    assert ownership_mapping([{"project_id": P, "owners": [A]}]) == {P: A}

@pytest.mark.parametrize("owners", [[], [A, B]])
def test_ambiguous_owner_requires_explicit_mapping(owners):
    with pytest.raises(ValueError, match="explicit owner"):
        ownership_mapping([{"project_id": P, "owners": owners}])

def test_explicit_verified_user_mapping_resolves_shared_workspace():
    assert ownership_mapping([{"project_id": P, "owners": [A, B]}], {P: B}, users={A, B}) == {P: B}

def test_override_cannot_point_to_unknown_identity():
    with pytest.raises(ValueError, match="unknown user"):
        ownership_mapping([{"project_id": P, "owners": [A]}], {P: B}, users={A})

def test_unknown_project_override_is_rejected():
    with pytest.raises(ValueError, match="unknown project"):
        ownership_mapping([{"project_id": P, "owners": [A]}], {Q: A}, users={A})

def test_input_is_not_mutated_and_duplicate_owner_rows_are_collapsed():
    rows=[{"project_id": P, "owners": [A, A]}]
    assert ownership_mapping(rows) == {P:A}
    assert rows[0]["owners"] == [A,A]


def test_github_current_user_does_not_require_a_public_email():
    from docweave.schemas.auth import CurrentUser
    assert CurrentUser(id=str(A), display_name="Person", verified_email=None, csrf_token="csrf").verified_email is None
