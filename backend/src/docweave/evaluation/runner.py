"""Run registered retrieval components against frozen development inputs."""

import json
from datetime import datetime, timezone
from docweave.db.sessions import tenant_session
from docweave.rag.contracts import RetrievalError, validate_vector
from docweave.rag.retrieval import retrieve_channels
from docweave.repositories.rag.evaluation import evaluation_snapshot
from docweave.evaluation.config import CORPUS, CONFIGURATIONS
from docweave.evaluation.fingerprint import source_fingerprint
from docweave.evaluation.metrics import ann_recall, support_recall


async def evaluate(dataset, *, actor, project_id, collection_ids, generation_id, recording, engine, denied_collection_ids=None):
    if not dataset._sha256 or not recording._sha256 or recording.generation_id != generation_id or recording.dataset_sha256 != dataset._sha256:
        raise ValueError("Incompatible vector recording")
    query_vectors = recording.vectors
    if set(query_vectors) != {case.id for case in dataset.cases}:
        raise ValueError("Every scenario needs one recorded query vector")
    for vector in query_vectors.values():
        validate_vector(vector)
    async with tenant_session(engine, actor_id=actor.user_id, workspace_id=actor.workspace_id) as session:
        generation, size, versions, database, extension = await evaluation_snapshot(session, project_id, collection_ids, generation_id)
    fixed_snapshots = sorted(str(row["version_id"]) for row in versions)
    documents = json.loads((CORPUS / "manifest.json").read_text())["documents"]
    matched_files = set()
    for version in versions:
        for document in documents:
            same_source = version["title"] == document["file"] or (document["source_url"] and version["source_url"] == document["source_url"])
            if same_source and version["content_hash"] == document["sha256"]:
                matched_files.add(document["file"])
    corpus_matches = len(matched_files) == len(documents) == len(versions)
    implementation = source_fingerprint()
    report = {"report_version": "retrieval-components-v2", "stage": "retrieval_components", "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset.version, "corpus_manifest_sha256": dataset.corpus_manifest_sha256,
        "retrieval_implementation_sha256": implementation["sha256"],
        "retrieval_implementation": implementation,
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
