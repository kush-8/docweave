"""Bounded evaluation datasets and recorded-vector inputs."""

import hashlib, json
from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field, PrivateAttr, model_validator
from docweave.schemas.common import StrictInput
from docweave.evaluation.config import CORPUS


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
