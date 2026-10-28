"""Draft API contract checks; these do not exercise a running backend."""

from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename


ID = "97f0d4a6-86c2-4bec-91cc-329f97d228d2"
OTHER_ID = "eab66ed0-d4d7-4911-9940-267507769ab0"
TIMESTAMP = "2026-10-29T00:00:00Z"
PROJECT = {"name": "Docs", "goal": "Explain retrieval", "stack": [{"technology": "python"}]}
TURN = {"message": "How does retrieval work?", "idempotency_key": "send-1"}
RESULT = {
    "kind": "answered",
    "text": "Use the retained documentation.",
    "citations": [{"id": ID, "evidence_url": "/api/v1/evidence/1", "document_version_id": ID}],
    "source_version_ids": [ID],
    "profile": {"id": "test-profile", "provider": "gemini", "model": "test-model", "backend": "test"},
    "usage": {"estimated_usd": "0.01", "metered_usd": None, "retained_uncertain_usd": "0.01"},
    "duration_ms": 0,
}


@pytest.fixture(scope="session")
def contract():
    path = Path(__file__).resolve().parents[1] / "openapi.yaml"
    spec, _ = read_from_filename(str(path))
    return spec


def schema_validator(contract, name):
    return Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
        format_checker=FormatChecker(),
    )


def test_openapi_document_is_valid(contract):
    validate(contract)


def test_private_operations_require_session_and_mutations_require_csrf(contract):
    public = {
        ("/health/live", "get"), ("/health/ready", "get"),
        ("/auth/login", "get"), ("/auth/callback", "get"),
        ("/catalog", "get"), ("/providers", "get"),
    }
    for path, item in contract["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                continue
            security = operation.get("security", contract.get("security", []))
            if (path, method) in public:
                continue
            assert security, f"{method.upper()} {path} allows anonymous access"
            for alternative in security:
                assert "sessionCookie" in alternative, f"{method.upper()} {path} bypasses session"
                if method in {"post", "put", "patch", "delete"}:
                    assert "csrfToken" in alternative, f"{method.upper()} {path} bypasses CSRF"


@pytest.mark.parametrize(("schema", "payload"), [
    ("ProjectInput", PROJECT),
    ("ProjectInput", {"name": "Docs", "goal": "Explain retrieval", "stack_review_id": ID}),
    ("ProjectPatch", {"expected_revision": 1, "goal": "Explain citations"}),
    ("ProjectPatch", {"expected_revision": 2, "architecture_notes": ""}),
    ("InvitationInput", {"email": "member@example.test", "role": "member"}),
    ("ConversationInput", {"provider_profile_id": "test-profile", "collection_ids": [ID, OTHER_ID]}),
    ("TurnInput", TURN),
    ("RetryInput", {"idempotency_key": "retry-1", "acknowledge_possible_charge": True}),
    ("DiscoveryInput", {"dependency_ids": [ID]}),
    ("ProcessingPolicyInput", {"expected_revision": 1, "approved_processor_ids": []}),
])
def test_request_schema_accepts_valid_payload(contract, schema, payload):
    schema_validator(contract, schema).validate(payload)


@pytest.mark.parametrize(("schema", "payload"), [
    ("ProjectInput", {"name": "Docs", "goal": "Explain retrieval"}),
    ("ProjectInput", {**PROJECT, "stack_review_id": ID}),
    ("ProjectInput", {**PROJECT, "stack": []}),
    ("ProjectInput", {**PROJECT, "stack": [{"technology": " "}]}),
    ("ProjectInput", {**PROJECT, "name": ""}),
    ("ProjectInput", {**PROJECT, "goal": " \n\t"}),
    ("ProjectInput", {**PROJECT, "workspace_id": ID}),
    ("ProjectInput", {**PROJECT, "stack": [{"technology": "python", "trusted": True}]}),
    ("ProjectPatch", {"goal": "Explain citations"}),
    ("ProjectPatch", {"expected_revision": 1}),
    ("ProjectPatch", {"expected_revision": 0, "goal": "Explain citations"}),
    ("ProjectPatch", {"expected_revision": True, "goal": "Explain citations"}),
    ("InvitationInput", {"email": "invalid", "role": "member"}),
    ("InvitationInput", {"email": "member@example.test", "role": "admin"}),
    ("ConversationInput", {}),
    ("ConversationInput", {"provider_profile_id": ""}),
    ("ConversationInput", {"provider_profile_id": "test-profile", "collection_ids": [ID, ID]}),
    ("ConversationInput", {"provider_profile_id": "test-profile", "collection_ids": ["bad-id"]}),
    ("TurnInput", {"message": "Question"}),
    ("TurnInput", {**TURN, "message": " \n\t"}),
    ("TurnInput", {**TURN, "idempotency_key": ""}),
    ("TurnInput", {**TURN, "provider_profile_id": "another-provider"}),
    ("RetryInput", {"idempotency_key": "retry-1", "acknowledge_possible_charge": "true"}),
    ("DiscoveryInput", {"dependency_ids": []}),
    ("DiscoveryInput", {"dependency_ids": [ID, ID]}),
    ("DiscoveryInput", {"dependency_ids": [f"00000000-0000-4000-8000-{i:012d}" for i in range(21)]}),
    ("ProcessingPolicyInput", {"approved_processor_ids": []}),
])
def test_request_schema_rejects_invalid_payload(contract, schema, payload):
    with pytest.raises(ValidationError):
        schema_validator(contract, schema).validate(payload)


@pytest.mark.parametrize("amount", ["0", "1", "0.01", "20.000001"])
def test_money_accepts_nonnegative_decimal_strings(contract, amount):
    schema_validator(contract, "Money").validate(amount)


@pytest.mark.parametrize("amount", [0, 0.01, True, None, "-1", "01", "1e-3", ".5", "1.", "NaN"])
def test_money_rejects_floats_and_nondecimal_values(contract, amount):
    with pytest.raises(ValidationError):
        schema_validator(contract, "Money").validate(amount)


@pytest.mark.parametrize("status", ["queued", "running", "completed", "failed", "completion_unknown", "blocked_policy"])
def test_turn_response_accepts_supported_states(contract, status):
    turn = {"id": ID, "conversation_id": OTHER_ID, "sequence": 1, "status": status,
            "request_id": "req-test", "created_at": TIMESTAMP}
    if status == "completed":
        turn.update(result=RESULT, context_revision=1, finished_at=TIMESTAMP)
    schema_validator(contract, "Turn").validate(turn)


@pytest.mark.parametrize("missing", ["result", "context_revision", "finished_at"])
def test_completed_turn_requires_result_and_completion_metadata(contract, missing):
    turn = {"id": ID, "conversation_id": OTHER_ID, "sequence": 1, "status": "completed",
            "request_id": "req-test", "created_at": TIMESTAMP, "result": RESULT,
            "context_revision": 1, "finished_at": TIMESTAMP}
    del turn[missing]
    with pytest.raises(ValidationError):
        schema_validator(contract, "Turn").validate(turn)


@pytest.mark.parametrize("status", ["queued", "running", "failed", "completion_unknown", "blocked_policy"])
def test_unfinished_turn_cannot_expose_result(contract, status):
    turn = {"id": ID, "conversation_id": OTHER_ID, "sequence": 1, "status": status,
            "request_id": "req-test", "created_at": TIMESTAMP, "result": RESULT}
    with pytest.raises(ValidationError):
        schema_validator(contract, "Turn").validate(turn)


def test_policy_blocked_turn_cannot_expose_user_message(contract):
    turn = {"id": ID, "conversation_id": OTHER_ID, "sequence": 1, "status": "blocked_policy",
            "request_id": "req-test", "created_at": TIMESTAMP, "message": "Private context"}
    with pytest.raises(ValidationError):
        schema_validator(contract, "Turn").validate(turn)


def test_usage_distinguishes_unconfirmed_cost_from_zero(contract):
    usage = {"estimated_usd": "0.01", "metered_usd": None, "retained_uncertain_usd": "0.01"}
    validator = schema_validator(contract, "TurnUsage")
    validator.validate(usage)
    validator.validate({**usage, "metered_usd": "0"})
    with pytest.raises(ValidationError):
        validator.validate({**usage, "metered_usd": 0})


def test_citation_requires_a_retained_document_version(contract):
    citation = deepcopy(RESULT["citations"][0])
    validator = schema_validator(contract, "CitationRef")
    validator.validate(citation)
    del citation["document_version_id"]
    with pytest.raises(ValidationError):
        validator.validate(citation)
