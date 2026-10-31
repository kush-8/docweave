"""Free-tier pilot input must come from the exact approved frozen corpus and queries."""

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def frozen(tmp_path):
    shutil.copytree(ROOT / "backend/tests/fixtures/ingestion", tmp_path / "corpus")
    shutil.copyfile(ROOT / "backend/eval/fixtures/pilot-v1.json", tmp_path / "pilot-v1.json")
    return tmp_path


def test_public_requests_are_derived_from_frozen_file_spans_and_query_ids(frozen):
    from docweave.evaluation.public_fixtures import PublicFixtures
    fixtures = PublicFixtures(frozen / "corpus", frozen / "pilot-v1.json")
    request = fixtures.document_request("synthetic-runbook.md", 0)
    assert request["content"]["parts"][0]["text"].startswith("title: none | text: #")
    assert fixtures.query_request("credentials")["content"]["parts"][0]["text"] == "task: search result | query: Where should the PostgreSQL connection URL be kept?"


@pytest.mark.parametrize("target", ["corpus/manifest.json", "corpus/synthetic-runbook.md", "pilot-v1.json"])
def test_mutating_any_approved_input_fails_closed(frozen, target):
    from docweave.rag.contracts import HostedError
    from docweave.evaluation.public_fixtures import PublicFixtures
    with (frozen / target).open("ab") as stream:
        stream.write(b"\nprivate text")
    with pytest.raises(HostedError, match="public_fixture_changed"):
        PublicFixtures(frozen / "corpus", frozen / "pilot-v1.json")


def test_unknown_paths_queries_and_span_indexes_cannot_supply_provider_input(frozen):
    from docweave.rag.contracts import HostedError
    from docweave.evaluation.public_fixtures import PublicFixtures
    fixtures = PublicFixtures(frozen / "corpus", frozen / "pilot-v1.json")
    for file, index in (("../secret.txt", 0), ("synthetic-runbook.md", -1), ("synthetic-runbook.md", True)):
        with pytest.raises(HostedError):
            fixtures.document_request(file, index)
    with pytest.raises(HostedError):
        fixtures.query_request("arbitrary private question")
