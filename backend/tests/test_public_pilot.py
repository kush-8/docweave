"""Public-only egress retains current consent and persistent one-time financial claims."""

import httpx
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import text

from docweave.core.paths import ROOT
from docweave.evaluation.public_fixtures import PublicFixtures
from docweave.rag.contracts import HostedError
from test_database import databases, test_urls  # noqa: F401
from test_retrieval import basis

pytestmark = pytest.mark.anyio


async def test_public_embedding_is_cached_but_revocation_still_blocks_reuse(databases):
    from docweave.services.public_pilot import prepare_public_pilot, PublicPilot
    owner, _ = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await prepare_public_pilot(owner, fixtures)
    assert context == await prepare_public_pilot(owner, fixtures)
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"embedding": {"values": basis()}})
    pilot = PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"}, transport=httpx.MockTransport(handler))
    assert await pilot.embed_document("synthetic-runbook.md", 0) == basis()
    assert await pilot.embed_document("synthetic-runbook.md", 0) == basis()
    assert len(calls) == 1
    async with owner.begin() as connection:
        assert await connection.scalar(text("SELECT purpose FROM app.compatibility_requests")) == "public_fixture"
        await connection.execute(text("DELETE FROM app.collection_processor_approvals WHERE collection_id=:id"), {"id": context["collection"]})
    with pytest.raises(HostedError):
        await pilot.embed_document("synthetic-runbook.md", 0)
    assert len(calls) == 1


async def test_unknown_private_text_cannot_become_public_pilot_input(databases):
    from docweave.services.public_pilot import prepare_public_pilot, PublicPilot
    owner, _ = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await prepare_public_pilot(owner, fixtures)
    async def handler(request):
        pytest.fail("Private input reached a provider")
    pilot = PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"}, transport=httpx.MockTransport(handler))
    with pytest.raises(HostedError):
        await pilot.embed_query("a private user question")


async def test_frozen_index_uses_normal_scope_and_atomic_publication(databases):
    from docweave.services.public_pilot import prepare_public_pilot, PublicPilot
    from docweave.rag.retrieval import retrieve_channels
    owner, runtime = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await prepare_public_pilot(owner, fixtures)
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"embedding": {"values": basis()}})
    pilot = PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"}, transport=httpx.MockTransport(handler))
    metrics = await pilot.build_index()
    assert len(metrics) == 3 and len(calls) > 3
    before = len(calls)
    await pilot.build_index()
    assert len(calls) == before
    result = await retrieve_channels(context["actor"], context["project"], "connection", collection_ids=[context["collection"]],
        generation_id=context["generation"], query_vector=basis(), engine=runtime)
    assert result["lexical"] and result["vector"] and len(result["snapshot_ids"]) == 3


async def test_all_registered_pilot_variants_run_with_scope_controls_and_no_paid_replay(databases):
    from docweave.services.public_pilot import prepare_public_pilot, PublicPilot
    from docweave.evaluation.public_pilot import evaluate_public_pilot
    owner, runtime = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await prepare_public_pilot(owner, fixtures)
    calls = []
    async def handler(request):
        calls.append(request)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, json={"embedding": {"values": basis()}})
        return httpx.Response(200, json={"model": "openai/gpt-oss-20b", "choices": [{"finish_reason": "stop", "message": {"content": '{"ordered_chunk_ids":[]}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
    pilot = PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"}, transport=httpx.MockTransport(handler))
    report = await evaluate_public_pilot(pilot, runtime)
    assert len(report["cases"]) == 13 and len(report["summary"]) == 16
    assert all(len(case["runs"]) == 16 for case in report["cases"])
    assert report["provider_vectors"] is False and report["pilot_gate_passed"] is False
    assert report["corpus_matches_manifest"] is True
    assert all(run["selected_tokens"] <= 6000 and len(run["selected_ids"]) <= 8 for case in report["cases"] for run in case["runs"])
    for case in report["cases"]:
        if case["kind"] in ("denied", "version"):
            assert all(run["control_passed"] and not run["selected_ids"] for run in case["runs"])
    before = len(calls)
    await evaluate_public_pilot(pilot, runtime)
    assert len(calls) == before


async def test_revocation_during_pacing_blocks_provider_egress(databases, monkeypatch):
    import docweave.services.public_pilot as module
    owner, _ = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await module.prepare_public_pilot(owner, fixtures)
    async def revoke(delay):
        async with owner.begin() as connection:
            await connection.execute(text("DELETE FROM app.collection_processor_approvals WHERE collection_id=:id"), {"id": context["collection"]})
    async def forbidden(*args, **kwargs):
        pytest.fail("Revoked context reached provider egress")
    monkeypatch.setattr(module, "asyncio", SimpleNamespace(sleep=revoke))
    monkeypatch.setattr(module, "provider_post", forbidden)
    pilot = module.PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"})
    with pytest.raises(HostedError):
        await pilot.embed_document("synthetic-runbook.md", 0)


async def test_version_control_uses_actual_eligible_index_metadata(databases):
    from docweave.services.public_pilot import prepare_public_pilot, PublicPilot
    from docweave.evaluation.public_pilot import evaluate_public_pilot
    owner, runtime = databases
    fixtures = PublicFixtures(ROOT / "backend/tests/fixtures/ingestion", ROOT / "backend/eval/fixtures/pilot-v1.json")
    context = await prepare_public_pilot(owner, fixtures)
    async def handler(request):
        return httpx.Response(200, json={"embedding": {"values": basis()}})
    pilot = PublicPilot(fixtures, context, engine=owner, api_keys={"gemini": "test", "groq": "test"}, transport=httpx.MockTransport(handler))
    await pilot.build_index()
    fixtures.dataset.cases = [case for case in fixtures.dataset.cases if case.required_docs_target]
    assert all(run["control_passed"] for run in (await evaluate_public_pilot(pilot, runtime))["cases"][0]["runs"])
    async with owner.begin() as connection:
        await connection.execute(text("UPDATE app.chunks SET provenance=jsonb_set(provenance,'{docs_target}','\"15\"'::jsonb) WHERE project_id=:id"), {"id": context["project"]})
    with pytest.raises(HostedError, match="unexpected_public_fixture_version"):
        await evaluate_public_pilot(pilot, runtime)
