"""Operator linking preserves UUIDs and refuses inferred or conflicting identities."""
from uuid import UUID
import json

import pytest
from sqlalchemy import text

from docweave.services import ownership
from tests.database.test_database import A, B, C, PA, PB, databases, test_urls  # noqa: F401


def plan():
    return {"identities": {str(A): {"issuer": "https://issuer.test", "subject": "actor-a",
        "github_id": 101, "token_env": "MIGRATION_TOKEN_A"},
        str(B): {"issuer": "https://issuer.test", "subject": "actor-b",
        "github_id": 102, "token_env": "MIGRATION_TOKEN_B"}},
        "projects": {str(PA): str(A), str(PB): str(B)}, "retained_users": [str(C)]}


@pytest.mark.parametrize("change", [
    lambda p: p["identities"][str(A)].update(github_id=True),
    lambda p: p["identities"][str(A)].update(github_id="101"),
    lambda p: p["identities"][str(A)].update(github_id=0),
    lambda p: p["identities"][str(A)].update(token_env="actual-token-value"),
    lambda p: p.update(retained_users=[str(A)]),
    lambda p: p.update(extra="ignored"),
])
def test_mapping_contract_rejects_unsafe_or_ambiguous_values(change):
    data = plan()
    change(data)
    with pytest.raises(ValueError, match="Invalid identity mapping"):
        ownership.parse_identity_plan(data)


class GitHub:
    async def user(self, token):
        return {"id": {"a": 101, "b": 102, "wrong": 999}[token], "login": "ignored"}


@pytest.mark.anyio
async def test_verified_mapping_dry_run_apply_and_repeat_preserve_records(databases):
    owner, _ = databases
    data = ownership.parse_identity_plan(plan())
    tokens = {"MIGRATION_TOKEN_A": "a", "MIGRATION_TOKEN_B": "b"}
    async with owner.begin() as connection:
        await connection.execute(text("INSERT INTO app.auth_sessions VALUES ('old-session',:actor,'old-encrypted-token',now()+interval '1 hour')"), {"actor": A})
    async with owner.begin() as connection:
        dry = await ownership.apply_identity_plan(connection, data, GitHub(), tokens, apply=False)
        assert dry["applied"] is False
        assert await connection.scalar(text("SELECT issuer FROM app.users WHERE id=:id"), {"id": A}) == "https://issuer.test"
    async with owner.begin() as connection:
        result = await ownership.apply_identity_plan(connection, data, GitHub(), tokens, apply=True)
        assert result["preserved"] is True
        assert await connection.scalar(text("SELECT subject FROM app.users WHERE id=:id"), {"id": A}) == "101"
        assert await connection.scalar(text("SELECT owner_user_id FROM app.projects WHERE id=:id"), {"id": PA}) == A
        assert await connection.scalar(text("SELECT count(*) FROM app.auth_sessions WHERE user_id=:id"), {"id": A}) == 0
        assert await connection.scalar(text("SELECT subject FROM app.users WHERE id=:id"), {"id": C}) == "no-membership"
        assert await connection.scalar(text("SELECT count(*) FROM app.collections")) == 2
    async with owner.begin() as connection:
        assert (await ownership.apply_identity_plan(connection, data, GitHub(), tokens, apply=True))["preserved"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["wrong_token", "stale_identity", "duplicate", "unresolved", "retained_owner"])
async def test_bad_mapping_is_atomic_and_never_links_by_email(databases, failure):
    owner, _ = databases
    raw = plan()
    tokens = {"MIGRATION_TOKEN_A": "a", "MIGRATION_TOKEN_B": "b"}
    if failure == "wrong_token":
        tokens["MIGRATION_TOKEN_B"] = "wrong"
    elif failure == "stale_identity":
        raw["identities"][str(B)]["subject"] = "changed"
    elif failure == "duplicate":
        raw["identities"][str(B)]["github_id"] = 101
        tokens["MIGRATION_TOKEN_B"] = "a"
    elif failure == "unresolved":
        raw["retained_users"] = []
    else:
        raw["identities"].pop(str(B))
        raw["retained_users"].append(str(B))
    async with owner.begin() as connection:
        with pytest.raises(ValueError):
            await ownership.apply_identity_plan(connection, ownership.parse_identity_plan(raw), GitHub(), tokens, apply=True)
        assert await connection.scalar(text("SELECT count(*) FROM app.users WHERE issuer='https://github.com'")) == 0
        assert await connection.scalar(text("SELECT count(*) FROM app.projects WHERE owner_user_id IS NOT NULL")) == 0


@pytest.mark.anyio
async def test_cli_identity_check_is_read_only_until_apply(databases, tmp_path, monkeypatch):
    from docweave import ownership as cli
    owner, _ = databases
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(plan()), encoding="utf-8")
    monkeypatch.setenv("MIGRATION_TOKEN_A", "a")
    monkeypatch.setenv("MIGRATION_TOKEN_B", "b")
    monkeypatch.setattr(cli, "GitHubClient", lambda settings: GitHub(), raising=False)
    result = await cli.check(identity_mapping_path=path, url_env="TEST_MIGRATION_DATABASE_URL")
    assert result["applied"] is False
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM app.users WHERE issuer='https://github.com'")) == 0


@pytest.mark.anyio
async def test_preservation_mismatch_rolls_back_even_if_caller_catches(databases, monkeypatch):
    from docweave.repositories import ownership as repository
    owner, _ = databases
    real_write = repository.write_identity_links
    async def corrupt(connection, identities, projects):
        await real_write(connection, identities, projects)
        await connection.execute(text("UPDATE app.projects SET goal='corrupted' WHERE id=:id"), {"id": PA})
    monkeypatch.setattr(repository, "write_identity_links", corrupt)
    async with owner.begin() as connection:
        with pytest.raises(ValueError, match="Preservation comparison failed"):
            await ownership.apply_identity_plan(connection, ownership.parse_identity_plan(plan()), GitHub(),
                {"MIGRATION_TOKEN_A": "a", "MIGRATION_TOKEN_B": "b"}, apply=True)
        assert await connection.scalar(text("SELECT goal FROM app.projects WHERE id=:id"), {"id": PA}) == "Learn retrieval"
        assert await connection.scalar(text("SELECT count(*) FROM app.users WHERE issuer='https://github.com'")) == 0


@pytest.mark.anyio
async def test_apply_refuses_running_jobs_until_workers_are_drained(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        conversation = await connection.scalar(text("INSERT INTO app.conversations(project_id) VALUES (:project) RETURNING id"), {"project": PA})
        await connection.execute(text("INSERT INTO app.personal_jobs(conversation_id,actor_id,kind,status) VALUES (:conversation,:actor,'sync','running')"),
            {"conversation": conversation, "actor": A})
    async with owner.begin() as connection:
        with pytest.raises(ValueError, match="Drain workers"):
            await ownership.apply_identity_plan(connection, ownership.parse_identity_plan(plan()), GitHub(),
                {"MIGRATION_TOKEN_A": "a", "MIGRATION_TOKEN_B": "b"}, apply=True)
        assert await connection.scalar(text("SELECT count(*) FROM app.users WHERE issuer='https://github.com'")) == 0
