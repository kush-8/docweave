"""Fingerprints bind both implementation bytes and repository-relative paths."""

from docweave.evaluation.fingerprint import source_fingerprint


def test_source_fingerprint_is_independent_of_input_order_and_working_directory(tmp_path, monkeypatch):
    first, second = tmp_path / "a.py", tmp_path / "b.py"
    first.write_bytes(b"first\n")
    second.write_bytes(b"second\n")
    fingerprint = source_fingerprint(tmp_path, [second, first])
    monkeypatch.chdir(tmp_path.parent)
    assert source_fingerprint(tmp_path, ["a.py", "b.py"]) == fingerprint
    assert list(fingerprint["files"]) == ["a.py", "b.py"]
    assert fingerprint["algorithm"] == "sha256-path-content-manifest-v1"


def test_source_fingerprint_changes_for_content_or_path_changes(tmp_path):
    first = tmp_path / "a.py"
    first.write_bytes(b"first\n")
    original = source_fingerprint(tmp_path, [first])
    first.write_bytes(b"changed\n")
    changed = source_fingerprint(tmp_path, [first])
    assert changed["sha256"] != original["sha256"]
    second = first.rename(tmp_path / "b.py")
    moved = source_fingerprint(tmp_path, [second])
    assert moved["sha256"] != changed["sha256"]
    assert moved["files"]["b.py"] == changed["files"]["a.py"]


def test_default_source_fingerprint_covers_all_stages_and_provider_contracts():
    files = source_fingerprint()["files"]
    assert "backend/src/docweave/rag/prompts.py" in files
    assert "backend/src/docweave/rag/chunking.py" in files
    assert "backend/src/docweave/repositories/rag/lexical.py" in files
    assert "backend/src/docweave/integrations/gemini.py" in files
    assert "backend/src/docweave/integrations/groq.py" in files
