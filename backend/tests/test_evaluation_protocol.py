"""Versioned development reports execute the real scoped retrieval service."""

import json
import hashlib
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from test_auth import auth_client  # noqa: F401
from test_collections import collections  # noqa: F401
from test_database import WB, databases, test_urls  # noqa: F401
from test_ingestion import FIXTURES, ingestion  # noqa: F401
from test_memberships import members  # noqa: F401
from test_retrieval import basis, index, indexed  # noqa: F401

pytestmark = pytest.mark.anyio
DATASET = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "pilot-v1.json"


async def test_pilot_dataset_has_ten_answerable_development_cases_and_separate_boundaries():
    from docweave.evaluation import load_dataset
    dataset = load_dataset(DATASET)
    assert len([case for case in dataset.cases if case.kind == "answerable"]) == 10
    assert {case.kind for case in dataset.cases} == {"answerable", "denied", "no_evidence", "version"}
    assert all(case.split == "development" for case in dataset.cases)
    for case in dataset.cases:
        for support in case.supports:
            raw = (FIXTURES / support.file).read_text(encoding="utf-8")
            assert raw[support.start:support.end] == support.quote


@pytest.mark.parametrize("mutation", ["held_out", "duplicate", "bad_span", "corpus_hash"])
async def test_dataset_rejects_unreviewable_or_incompatible_inputs(tmp_path, mutation):
    from docweave.evaluation import load_dataset
    value = json.loads(DATASET.read_text())
    if mutation == "held_out":
        value["cases"][0]["split"] = "held_out"
    elif mutation == "duplicate":
        value["cases"].append(value["cases"][0])
    elif mutation == "bad_span":
        value["cases"][0]["supports"][0]["quote"] = "Invented supporting evidence"
    else:
        value["corpus_manifest_sha256"] = "0" * 64
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_dataset(path)


async def test_metric_denominators_distinguish_ann_recall_and_supporting_recall():
    from docweave.evaluation import ann_recall
    assert ann_recall(["a", "b"], ["a", "c"], 10) == {"value": 0.5, "matched": 1, "denominator": 2}
    assert ann_recall([], [], 10) == {"value": None, "matched": 0, "denominator": 0}


async def test_supporting_recall_requires_the_correct_source_span():
    from docweave.evaluation import load_dataset, support_recall
    case = load_dataset(DATASET).cases[0]
    support = case.supports[0]
    hit = {"quote": support.quote, "provenance": {"document_title": support.file}, "source_url": None,
        "locator": {"start": support.end + 10, "end": support.end + 10 + len(support.quote)}}
    assert support_recall(case, [hit])["matched"] == 0
    hit["locator"] = {"start": support.start, "end": support.end}
    assert support_recall(case, [hit])["matched"] == 1


async def test_report_runs_all_registered_components_without_claiming_semantic_quality(indexed, tmp_path):
    from docweave.evaluation import evaluate, load_dataset, load_recording
    c = indexed
    await index(c, b"Alpha connection instructions.\n")
    dataset = load_dataset(DATASET)
    vectors = {case.id: basis() for case in dataset.cases}
    path = tmp_path / "recording.json"
    path.write_text(json.dumps({"recording_version": "recorded-vectors-v1", "generation_id": str(c["generation"]),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(), "provenance": "recorded_fixture", "vectors": vectors}))
    recording = load_recording(path)
    async with c["owner"].connect() as connection:
        denied = await connection.scalar(text("SELECT id FROM app.collections WHERE workspace_id=:w LIMIT 1"), {"w": WB})
    report = await evaluate(dataset, actor=c["actor"], project_id=UUID(c["project"]), collection_ids=[UUID(c["collection"])],
        generation_id=c["generation"], recording=recording, engine=c["runtime"], denied_collection_ids=[denied])
    assert len(report["configurations"]) == 8
    assert len(report["cases"]) == len(dataset.cases)
    assert report["semantic_quality_evidence"] is False and report["stage"] == "retrieval_components"
    assert report["generation"]["model"] == "test-recorded-768"
    assert report["corpus_matches_manifest"] is False
    assert report["query_recording_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["physical_shared_index_size_bytes"] > 0
    denied_case = next(case for case in report["cases"] if case["kind"] == "denied")
    assert all(run["status"] == "denied" for run in denied_case["runs"])
    normal = next(case for case in report["cases"] if case["kind"] == "answerable")
    assert len(normal["runs"]) == 4
    for run in normal["runs"]:
        assert run["plans"]["vector"] and run["latency_ms"]["vector"] >= 0
        assert run["ann_recall_at_30"]["denominator"] == 1
        assert run["vector_underfilled_vs_eligible"] is False


async def test_cli_evaluates_the_frozen_corpus_and_writes_an_atomic_report(indexed, tmp_path):
    from docweave.evaluation import load_dataset
    from docweave.ingestion import ROOT
    from docweave.retrieval import index_document
    from docweave.settings import database_url
    from test_ingestion import work
    c = indexed
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    build = []
    for fixture in manifest["documents"]:
        response = await c["admin"].post(f'/api/v1/collections/{c["collection"]}/documents',
            files={"file": (fixture["file"], (FIXTURES / fixture["file"]).read_bytes(), fixture["media_type"])}, headers=c["headers"])
        assert response.status_code == 202
        accepted = response.json()
        await work(c, accepted["job_id"])
        async def recorded(bodies):
            return [basis() for body in bodies]
        build.append(await index_document(c["actor"], UUID(accepted["document_id"]), c["generation"],
            worker_engine=c["worker"], store=c["store"], embedder=recorded))
    dataset = load_dataset(DATASET)
    vectors = tmp_path / "vectors.json"
    vectors.write_text(json.dumps({"recording_version": "recorded-vectors-v1", "generation_id": str(c["generation"]),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(), "provenance": "recorded_fixture",
        "vectors": {case.id: basis() for case in dataset.cases}, "build_metrics": build}))
    output = tmp_path / "report.json"
    output.write_text("old report must survive a failed write")
    async with c["owner"].connect() as connection:
        denied = await connection.scalar(text("SELECT id FROM app.collections WHERE workspace_id=:w LIMIT 1"), {"w": WB})
    environment = {**os.environ, "DATABASE_URL": database_url("TEST_DATABASE_URL").render_as_string(hide_password=False),
        "PYTHONPATH": str(ROOT / "backend" / "src")}
    process = await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "docweave.evaluation", "--actor", str(c["actor"].user_id),
        "--workspace", str(c["actor"].workspace_id), "--project", c["project"], "--generation", str(c["generation"]),
        "--collection", c["collection"], "--denied-collection", str(denied), "--vectors", str(vectors), "--output", str(output)],
        env=environment, capture_output=True, timeout=60)
    assert process.returncode == 0, process.stderr.decode(errors="replace")[-1000:]
    report = json.loads(output.read_text())
    assert report["corpus_matches_manifest"] is True
    assert len(report["build_metrics"]) == 3 and all(item["publish_ms"] >= 0 for item in report["build_metrics"])
    assert len(report["cases"]) == 13 and report["semantic_quality_evidence"] is False
    # Retain this controlled, synthetic/public smoke artifact outside tracked fixtures.
    (ROOT / "backend" / "eval" / "reports" / "component-smoke.json").write_text(output.read_text())


@pytest.mark.parametrize("wrong", ["generation", "dataset", "changed_question"])
async def test_recordings_must_match_the_requested_generation_and_question_file(tmp_path, wrong):
    from uuid import uuid4
    from docweave.evaluation import evaluate, load_dataset, load_recording
    dataset = load_dataset(DATASET)
    if wrong == "changed_question":
        changed = json.loads(DATASET.read_text())
        changed["cases"][0]["query"] = "A revised question retaining its scenario ID"
        changed_path = tmp_path / "changed.json"
        changed_path.write_text(json.dumps(changed))
        dataset = load_dataset(changed_path)
    generation = uuid4()
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps({"recording_version": "recorded-vectors-v1",
        "generation_id": str(uuid4() if wrong == "generation" else generation),
        "dataset_sha256": "0" * 64 if wrong == "dataset" else hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "provenance": "recorded_fixture", "vectors": {case.id: basis() for case in dataset.cases}}))
    with pytest.raises(ValueError, match="recording"):
        await evaluate(dataset, actor=None, project_id=uuid4(), collection_ids=[], generation_id=generation,
            recording=load_recording(path), engine=None)


async def test_failed_report_serialization_preserves_the_previous_artifact(tmp_path):
    from docweave.evaluation import write_report
    path = tmp_path / "report.json"
    path.write_text('{"previous": true}\n')
    with pytest.raises(ValueError):
        write_report(path, {"invalid_metric": float("nan")})
    assert path.read_text() == '{"previous": true}\n'
    assert list(tmp_path.iterdir()) == [path]
