"""Role reconciliation preserves financial history without authorizing legacy dispatch."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from test_budget import allowance
from test_budget import profile
from test_budget import reserve
from test_budget import settle
from test_database import databases
from test_database import migrate
from test_database import test_urls  # noqa: F401

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(("role", "provider", "eligible"), [
    ("embedding", "gemini", True), ("embedding", "groq", False),
    ("generation", "groq", True), ("generation", "gemini", False),
    ("reranking", "groq", True), ("reranking", "gemini", False),
    ("query_resolution", "groq", True), ("summarization", "groq", True),
    ("generation", "huggingface", False),
])
async def test_only_selected_providers_can_admit_each_hosted_role(databases, role, provider, eligible):
    owner, _ = databases
    identity = await profile(owner, role=role, provider=provider)
    async with owner.connect() as connection:
        reason = await connection.scalar(text("SELECT app.profile_disabled_reason(:id)"), {"id": identity})
    assert reason == (None if eligible else "provider_unavailable")


async def test_generation_requires_gemini_embedding_and_groq_reranking_processors(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        await connection.execute(text("""INSERT INTO app.processors(id,provider,backend,roles) VALUES
            ('test:role:embedding','gemini','fake-google','["embedding"]'),
            ('test:role:generation','groq','fake-groq','["generation"]'),
            ('test:role:reranking','groq','fake-groq','["reranking"]') ON CONFLICT DO NOTHING"""))
        await connection.execute(text("UPDATE app.processors SET enabled=true WHERE id LIKE 'test:role:%'"))
    complete = await profile(owner, processors=["test:role:embedding", "test:role:generation", "test:role:reranking"])
    missing = await profile(owner, processors=["test:role:embedding", "test:role:generation"])
    async with owner.connect() as connection:
        assert await connection.scalar(text("SELECT app.profile_disabled_reason(:id)"), {"id": complete}) is None
        assert await connection.scalar(text("SELECT app.profile_disabled_reason(:id)"), {"id": missing}) == "processor_unavailable"


async def test_reconciliation_preserves_original_profile_and_charge_identity(databases, test_urls):
    owner, runtime = databases
    await migrate(test_urls[1], "0009_retrieval", downgrade=True)
    try:
        identity = await profile(owner, provider="gemini")
        await allowance(owner)
        original = await reserve(runtime, identity)
    finally:
        await migrate(test_urls[1], "head")
    async with owner.connect() as connection:
        row = (await connection.execute(text("SELECT id,provider,app.profile_disabled_reason(id) reason FROM app.provider_profiles WHERE id=:id"), {"id": identity})).one()
        assert row.id == identity and row.provider == "gemini" and row.reason == "provider_unavailable"
    replay = await reserve(runtime, identity)
    assert replay.id == original.id and not replay.created
    confirmed = await settle(runtime, original, Decimal("0.2"))
    assert confirmed.profile_id == identity and confirmed.charged_usd == Decimal("0.2")
