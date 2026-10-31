"""Versioned development corpus and registered retrieval configurations."""

from docweave.core.paths import ROOT


CORPUS = ROOT / "backend" / "tests" / "fixtures" / "ingestion"
DEFAULT_DATASET = ROOT / "backend" / "eval" / "fixtures" / "pilot-v1.json"
CONFIGURATIONS = ["native_only", "bm25_only", "exact_only", "hnsw_only", "native_exact", "native_hnsw", "bm25_exact", "bm25_hnsw"]
