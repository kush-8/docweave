"""Approved public pilot inputs are derived from pinned bytes, never caller-supplied text."""

import hashlib, json
from pathlib import Path
from docweave.evaluation import Dataset
from docweave.rag.contracts import HostedError
from docweave.integrations.gemini import embedding_request
from docweave.rag.parsing import parse_text


MANIFEST_SHA256 = "82f486f552029bfa5cc7b23a3fae174cc04b13ec459f2470a676ed10fe55c616"
DATASET_SHA256 = "0dab6cf6baf9b5e0217c96264f36fe5561a8f5a9eaaa82e9c77f080c03debe3c"


def pinned_bytes(path, expected):
    try:
        with Path(path).open("rb") as file:
            raw = file.read(1024 * 1024 + 1)
    except OSError:
        raise HostedError("public_fixture_changed") from None
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise HostedError("public_fixture_changed")
    return raw


class PublicFixtures:
    def __init__(self, corpus, dataset):
        corpus = Path(corpus)
        manifest = json.loads(pinned_bytes(corpus / "manifest.json", MANIFEST_SHA256))
        self.dataset = Dataset.model_validate_json(pinned_bytes(dataset, DATASET_SHA256))
        self._documents = {item["file"]: parse_text(pinned_bytes(corpus / item["file"], item["sha256"]), item["media_type"])
            for item in manifest["documents"]}
        self._cases = {case.id: case for case in self.dataset.cases}

    def document_request(self, file, chunk_index):
        if type(file) is not str or file not in self._documents or type(chunk_index) is not int:
            raise HostedError("unknown_public_fixture")
        document = self._documents[file]
        if not 0 <= chunk_index < len(document["chunks"]):
            raise HostedError("unknown_public_fixture_span")
        span = document["chunks"][chunk_index]
        return embedding_request(document["text"][span["start"]:span["end"]], "document")

    def query_request(self, case_id):
        if type(case_id) is not str or case_id not in self._cases:
            raise HostedError("unknown_public_fixture_query")
        case = self._cases[case_id]
        if case.scope != "authorized":
            raise HostedError("public_fixture_scope_not_authorized")
        return embedding_request(case.query, "query")
