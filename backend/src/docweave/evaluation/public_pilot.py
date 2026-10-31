"""Frozen public retrieval pilot through actual RLS queries and accounted hosted requests."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, UTC
from dotenv import dotenv_values
from docweave.compatibility import operator_url
from docweave.core.paths import ROOT
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.db.sessions import tenant_session
from docweave.evaluation.config import CORPUS, DEFAULT_DATASET, CONFIGURATIONS
from docweave.evaluation.public_fixtures import PublicFixtures, MANIFEST_SHA256, DATASET_SHA256
from docweave.evaluation.metrics import support_recall, ann_recall
from docweave.evaluation.reports import write_report
from docweave.evaluation.fingerprint import source_fingerprint
from docweave.rag.contracts import HostedError, RetrievalError
from docweave.rag.fusion import fuse_channels
from docweave.rag.reranking import ranked_evidence
from docweave.rag.retrieval import retrieve_channels
from docweave.rag.tokenization import TOKENIZER, count_evidence_tokens
from docweave.repositories.compatibility import retained_cost
from docweave.repositories.rag.evaluation import evaluation_snapshot
from docweave.repositories.public_pilot import compatible_chunks
from docweave.services.public_pilot import prepare_public_pilot, PublicPilot


async def evaluate_public_pilot(pilot, runtime, *, progress=None):
    c, fixtures = pilot.context, pilot.fixtures
    build = await pilot.build_index()
    async with tenant_session(runtime, actor_id=c["actor"].user_id, workspace_id=c["actor"].workspace_id) as session:
        generation, size, versions, database, extension = await evaluation_snapshot(session, c["project"], [c["collection"]], c["generation"])
    expected = {str(d["version"]): d["hash"] for d in c["documents"].values()}
    if {str(row["version_id"]): row["content_hash"] for row in versions} != expected:
        raise HostedError("public_fixture_index_changed")
    implementation_paths = [*(ROOT / "backend/src/docweave").rglob("*.py"), *(ROOT / "backend/alembic").rglob("*.py"),
        ROOT / "backend/pyproject.toml", ROOT / "backend/uv.lock"]
    report = {"version": "public-retrieval-pilot-v1", "created_at": datetime.now(UTC).isoformat(), "development_only": True,
        "human_label_review": fixtures.dataset.human_label_review, "answer_quality_evidence": False, "production_default_selected": False,
        "corpus_manifest_sha256": MANIFEST_SHA256, "dataset_sha256": DATASET_SHA256, "tokenizer": TOKENIZER,
        "rerank_input_budget": {"max_candidates": 20, "max_serialized_request_tokens": 3000, "whole_chunks_only": True, "completion_limit": 4096},
        "generation": dict(generation), "captured_versions": [dict(row) for row in versions], "corpus_matches_manifest": True,
        "physical_shared_index_size_bytes": size, "database": database, "pgvector_version": extension, "build_metrics": build,
        "implementation": source_fingerprint(paths=implementation_paths), "cases": [], "summary": {}}
    fixed_versions = sorted(expected)
    for case in fixtures.dataset.cases:
        captured = {"id": case.id, "kind": case.kind, "components": {}, "runs": []}
        report["cases"].append(captured)
        if case.scope != "authorized" or case.required_docs_target:
            if case.required_docs_target:
                async with tenant_session(runtime, actor_id=c["actor"].user_id, workspace_id=c["actor"].workspace_id) as session:
                    count = await compatible_chunks(session, c, case.required_docs_target)
                captured["observed_compatible_chunks"] = count
                if count:
                    raise HostedError("unexpected_public_fixture_version")
            for name in CONFIGURATIONS:
                if case.scope == "inaccessible":
                    try:
                        await retrieve_channels(c["actor"], c["project"], case.query, collection_ids=[c["denied_collection"]],
                            generation_id=c["generation"], query_vector=[1.0] + [0.0] * 767, engine=runtime)
                    except RetrievalError as error:
                        if str(error) != "not_found":
                            raise
                    else:
                        raise HostedError("public_fixture_isolation_failed")
                for rerank in (False, True):
                    captured["runs"].append({"configuration": name, "reranked": rerank, "status": "denied" if case.scope == "inaccessible" else "no_compatible_version",
                        "selected_ids": [], "selected_tokens": 0, "control_passed": True})
            continue
        vector = await pilot.embed_query(case.id)
        captured["query_vector_sha256"] = hashlib.sha256(json.dumps(vector).encode()).hexdigest()
        pairs = {}
        exact = []
        for lexical in ("native", "bm25"):
            for strategy in ("exact", "hnsw"):
                result = await retrieve_channels(c["actor"], c["project"], case.query, collection_ids=[c["collection"]], generation_id=c["generation"],
                    query_vector=vector, engine=runtime, lexical=lexical, vector=strategy, explain=True)
                if result["snapshot_ids"] != fixed_versions:
                    raise HostedError("public_fixture_index_changed")
                pairs[lexical + "_" + strategy] = result
                identities = [str(hit["chunk_id"]) for hit in result["vector"]]
                if strategy == "exact":
                    exact = identities
                captured["components"][lexical + "_" + strategy] = {"plans": result["plans"], "latency_ms": result["latency_ms"], "settings": result["settings"],
                    "candidate_ids": {channel: [str(hit["chunk_id"]) for hit in result[channel]] for channel in ("lexical", "vector")},
                    "eligible_count": result["eligible_count"], "underfilled": len(identities) < min(30, result["eligible_count"]), "ann_recall_at_30": ann_recall(exact, identities, 30)}
        for name in CONFIGURATIONS:
            if name.endswith("_only"):
                channel = name.removesuffix("_only")
                source = pairs[("bm25" if channel == "bm25" else "native") + ("_hnsw" if channel == "hnsw" else "_exact")]
                candidates = source["lexical" if channel in ("native", "bm25") else "vector"][:20]
            else:
                candidates = fuse_channels(pairs[name])
            for rerank in (False, True):
                started = time.perf_counter()
                ranking = await pilot.rerank(case.id, candidates) if rerank else None
                ordered = ranking["ordered_chunk_ids"] if rerank else [str(hit["chunk_id"]) for hit in candidates]
                selected = ranked_evidence(candidates, ordered, count_evidence_tokens)
                await pilot.release(selected, reranked=rerank)
                recall = support_recall(case, selected)
                captured["runs"].append({"configuration": name, "reranked": rerank, "status": "ok", "selected_ids": [str(hit["chunk_id"]) for hit in selected],
                    "selected_tokens": sum(count_evidence_tokens(hit["quote"]) for hit in selected), "selected_evidence": selected, "supporting_recall_at_8": recall,
                    "rerank_input_ids": ranking["input_chunk_ids"] if rerank else None,
                    "finalization_ms": (time.perf_counter() - started) * 1000, "control_passed": not selected if case.kind == "no_evidence" else True})
        if progress:
            progress(case.id)
    for name in CONFIGURATIONS:
        for rerank in (False, True):
            runs = [(case, next(run for run in case["runs"] if run["configuration"] == name and run["reranked"] == rerank)) for case in report["cases"]]
            answerable = [run for case, run in runs if case["kind"] == "answerable"]
            supported = sum(run["supporting_recall_at_8"]["matched"] == run["supporting_recall_at_8"]["denominator"] for run in answerable)
            controls = all(run["control_passed"] for case, run in runs if case["kind"] != "answerable")
            report["summary"][name + ("+rerank" if rerank else "+rrf_or_single")] = {"supported_questions": supported, "denominator": len(answerable), "controls_passed": controls,
                "pilot_gate_passed": supported >= 9 and len(answerable) == 10 and controls}
    async with pilot.engine.connect() as connection:
        report["retained_usd"] = str(await retained_cost(connection, c["actor"].workspace_id))
    report["pilot_gate_passed"] = any(item["pilot_gate_passed"] for item in report["summary"].values())
    report["provider_vectors"] = pilot.transport is None
    return report


async def main():
    fixtures = PublicFixtures(CORPUS, DEFAULT_DATASET)
    owner, runtime = make_engine(operator_url()), make_engine(database_url("DATABASE_URL"))
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    keys = {provider: values.get(provider.upper() + "_API_KEY") for provider in ("gemini", "groq")}
    try:
        context = await prepare_public_pilot(owner, fixtures)
        pilot = PublicPilot(fixtures, context, engine=owner, api_keys=keys)
        report = await evaluate_public_pilot(pilot, runtime, progress=lambda case: print("Completed public fixture: " + case, flush=True))
        write_report(ROOT / "backend/eval/reports/public-pilot-v1.json", report)
        print(json.dumps({"pilot_gate_passed": report["pilot_gate_passed"], "retained_usd": report["retained_usd"], "summary": report["summary"]}, indent=2))
    finally:
        await owner.dispose()
        await runtime.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute the approved hash-bound public fixture pilot under its separate US$1 cap.")
    parser.parse_args()
    asyncio.run(main())
