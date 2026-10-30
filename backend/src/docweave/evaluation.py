"""Versioned development retrieval-component reports; no generation, judges or paid calls."""

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr, model_validator
from sqlalchemy import text

from docweave.db import make_engine, tenant_session
from docweave.ingestion import ROOT
from docweave.policy import Actor
from docweave.projects import StrictInput
from docweave.retrieval import RetrievalError, retrieve_channels, vector_literal
from docweave.settings import database_url

CORPUS = ROOT / "backend" / "tests" / "fixtures" / "ingestion"
DEFAULT_DATASET = ROOT / "backend" / "eval" / "fixtures" / "pilot-v1.json"
CONFIGURATIONS = ["native_only", "bm25_only", "exact_only", "hnsw_only", "native_exact", "native_hnsw", "bm25_exact", "bm25_hnsw"]


class Support(StrictInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    file: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1)


class Scenario(StrictInput):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    family_id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    split: Literal["development"]
    kind: Literal["answerable", "denied", "no_evidence", "version"]
    scope: Literal["authorized", "inaccessible", "empty"]
    query: str = Field(min_length=1, max_length=4096)
    supports: list[Support]
    required_docs_target: str | None = None


class Dataset(StrictInput):
    _sha256: str = PrivateAttr(default="")
    version: str = Field(min_length=1, max_length=64)
    human_label_review: Literal["pending"]
    corpus_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cases: list[Scenario] = Field(min_length=1, max_length=150)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate scenario ID")
        if any(case.kind == "answerable" and not case.supports for case in self.cases):
            raise ValueError("Answerable cases need supporting spans")
        return self


class RecordedVectors(StrictInput):
    _sha256: str = PrivateAttr(default="")
    recording_version: Literal["recorded-vectors-v1"]
    generation_id: UUID
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance: Literal["recorded_fixture", "recorded_provider"]
    vectors: dict[str, list] = Field(min_length=1, max_length=150)
    build_metrics: list[dict] | None = None


def load_dataset(path):
    with Path(path).open("rb") as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Dataset too large")
    dataset = Dataset.model_validate_json(raw)
    dataset._sha256 = hashlib.sha256(raw).hexdigest()
    manifest = (CORPUS / "manifest.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != dataset.corpus_manifest_sha256:
        raise ValueError("Corpus manifest changed")
    documents = {item["file"]: item for item in json.loads(manifest)["documents"]}
    for case in dataset.cases:
        for support in case.supports:
            if support.file not in documents:
                raise ValueError("Unknown corpus file")
            raw = (CORPUS / support.file).read_bytes()
            if hashlib.sha256(raw).hexdigest() != documents[support.file]["sha256"]:
                raise ValueError("Corpus bytes changed")
            if raw.decode("utf-8")[support.start:support.end] != support.quote:
                raise ValueError("Supporting span is not exact")
    return dataset


def load_recording(path):
    with Path(path).open("rb") as file:
        raw = file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Vector recording too large")
    recording = RecordedVectors.model_validate_json(raw)
    recording._sha256 = hashlib.sha256(raw).hexdigest()
    return recording


def ann_recall(exact, approximate, k):
    reference = set(exact[:k])
    matched = len(reference.intersection(approximate[:k]))
    return {"value": matched / len(reference) if reference else None, "matched": matched, "denominator": len(reference)}


def support_recall(case, hits):
    documents = {item["file"]: item for item in json.loads((CORPUS / "manifest.json").read_text())["documents"]}
    matched = 0
    for support in case.supports:
        source_url = documents[support.file]["source_url"]
        for hit in hits[:10]:
            same_source = hit["provenance"].get("document_title") == support.file or (source_url and hit["source_url"] == source_url)
            if same_source and support.quote in hit["quote"] and hit["locator"]["start"] <= support.start < support.end <= hit["locator"]["end"]:
                matched += 1
                break
    return {"value": matched / len(case.supports) if case.supports else None, "matched": matched, "denominator": len(case.supports)}


async def evaluate(dataset, *, actor, project_id, collection_ids, generation_id, recording, engine, denied_collection_ids=None):
    if not dataset._sha256 or not recording._sha256 or recording.generation_id != generation_id or recording.dataset_sha256 != dataset._sha256:
        raise ValueError("Incompatible vector recording")
    query_vectors = recording.vectors
    if set(query_vectors) != {case.id for case in dataset.cases}:
        raise ValueError("Every scenario needs one recorded query vector")
    for vector in query_vectors.values():
        vector_literal(vector)
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        await session.execute(text("SELECT set_config('docweave.generation_id',:id,true)"), {"id": str(generation_id)})
        generation = (await session.execute(text("SELECT * FROM app.index_generations WHERE id=:id"), {"id": generation_id})).mappings().first()
        if generation is None:
            raise ValueError("Unknown generation")
        size = await session.scalar(text("SELECT pg_relation_size('app.ix_chunks_embedding_hnsw')"))
        versions = (await session.execute(text("SELECT * FROM app.evaluation_versions(:project,:generation,CAST(:collections AS uuid[]))"),
            {"project": project_id, "collections": collection_ids, "generation": generation_id})).mappings().all()
        database = await session.scalar(text("SELECT version()"))
        extension = await session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    fixed_snapshots = sorted(str(row["version_id"]) for row in versions)
    documents = json.loads((CORPUS / "manifest.json").read_text())["documents"]
    matched_files = set()
    for version in versions:
        for document in documents:
            same_source = version["title"] == document["file"] or (document["source_url"] and version["source_url"] == document["source_url"])
            if same_source and version["content_hash"] == document["sha256"]:
                matched_files.add(document["file"])
    corpus_matches = len(matched_files) == len(documents) == len(versions)
    report = {"report_version": "retrieval-components-v1", "stage": "retrieval_components", "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset.version, "corpus_manifest_sha256": dataset.corpus_manifest_sha256,
        "retrieval_implementation_sha256": hashlib.sha256(Path(__file__).with_name("retrieval.py").read_bytes()).hexdigest(),
        "lexical_configuration": {"native": {"configuration": "english", "ranking": "ts_rank_cd"},
            "bm25": {"version": "sql-bm25-ident-v1", "k1": 1.2, "b": 0.75, "statistics": "authorized_chunks_only"}},
        "human_label_review": dataset.human_label_review, "generation": dict(generation), "snapshot_ids": fixed_snapshots,
        "vector_provenance": recording.provenance, "query_recording_sha256": recording._sha256, "dataset_sha256": dataset._sha256,
        "semantic_quality_evidence": False, "corpus_matches_manifest": corpus_matches,
        "captured_versions": [dict(row) for row in versions],
        "physical_shared_index_size_bytes": size, "build_metrics": recording.build_metrics, "database": database, "pgvector_version": extension,
        "configurations": CONFIGURATIONS, "hybrid_execution": "registered_components_only; fusion/reranking belongs to 3C", "cases": []}
    for case in dataset.cases:
        scopes = collection_ids if case.scope == "authorized" else denied_collection_ids if case.scope == "inaccessible" else []
        captured = {"id": case.id, "family_id": case.family_id, "kind": case.kind, "runs": []}
        report["cases"].append(captured)
        for lexical in ("native", "bm25"):
            exact_ids = []
            for vector in ("exact", "hnsw"):
                run = {"configuration": lexical + "_" + vector}
                captured["runs"].append(run)
                if scopes is None:
                    run.update(status="not_run", reason="inaccessible_scope_fixture_required")
                    continue
                try:
                    result = await retrieve_channels(actor, project_id, case.query, collection_ids=scopes, generation_id=generation_id,
                        query_vector=query_vectors[case.id], engine=engine, lexical=lexical, vector=vector, explain=True)
                    if case.scope == "authorized" and result["snapshot_ids"] != fixed_snapshots:
                        raise RetrievalError("scope_changed")
                except RetrievalError as error:
                    run.update(status="denied" if case.kind == "denied" and str(error) == "not_found" else "error", code=str(error))
                    continue
                ranked = {channel: [str(hit["chunk_id"]) for hit in result[channel]] for channel in ("lexical", "vector")}
                if vector == "exact":
                    exact_ids = ranked["vector"]
                wanted = min(30, result["eligible_count"])
                run.update(status="candidates_only", candidate_ids=ranked,
                    scores={channel: [hit["score"] for hit in result[channel]] for channel in ranked},
                    plans=result["plans"], latency_ms=result["latency_ms"], settings={**result["settings"], "jit": "off"},
                    eligible_count=result["eligible_count"], vector_fewer_than_requested=len(ranked["vector"]) < 30,
                    vector_underfilled_vs_eligible=len(ranked["vector"]) < wanted,
                    ann_recall_at_30=ann_recall(exact_ids, ranked["vector"], 30),
                    supporting_recall_at_10={channel: support_recall(case, result[channel]) for channel in ranked})
                if case.required_docs_target:
                    hits = {hit["chunk_id"]: hit for channel in ranked for hit in result[channel]}
                    run["wrong_or_unknown_version_hits"] = sum(hit["provenance"].get("docs_target") != case.required_docs_target for hit in hits.values())
    return report


def write_report(path, report):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(report, file, indent=2, default=str, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


async def main(args):
    dataset = load_dataset(args.dataset)
    recording = load_recording(args.vectors)
    engine = make_engine(database_url("DATABASE_URL"))
    try:
        report = await evaluate(dataset, actor=Actor(args.actor, args.workspace), project_id=args.project, collection_ids=args.collection,
            generation_id=args.generation, recording=recording, denied_collection_ids=args.denied_collection, engine=engine)
        write_report(args.output, report)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("actor", "workspace", "project", "generation"):
        parser.add_argument("--" + name, type=UUID, required=True)
    parser.add_argument("--collection", type=UUID, action="append", required=True)
    parser.add_argument("--denied-collection", type=UUID, action="append")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    try:
        asyncio.run(main(parser.parse_args()))
    except (ValueError, RetrievalError, OSError):
        parser.exit(2, "Invalid, unavailable or incompatible evaluation inputs.\n")
