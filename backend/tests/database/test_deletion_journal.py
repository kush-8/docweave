from uuid import uuid4

import pytest


def test_journal_is_content_free_idempotent_and_detects_changes(tmp_path):
    from docweave.storage.deletions import DeletionJournal
    journal = DeletionJournal(tmp_path)
    identity, project, artifact = uuid4(), uuid4(), uuid4()
    key = journal.record("document", identity, project, [artifact])
    assert journal.record("document", identity, project, [artifact]) == key
    assert journal.entries() == {key: {"format": "deletion-v1", "kind": "document",
        "id": str(identity), "project_id": str(project), "artifacts": [str(artifact)]}}
    with pytest.raises(ValueError):
        journal.record("unknown", identity, project, [])
    (tmp_path / f"{key}.json").write_text("private forged text")
    with pytest.raises(ValueError):
        journal.entries()


def test_missing_journal_is_not_silently_recreated_for_reading(tmp_path):
    from docweave.storage.deletions import DeletionJournal
    journal = DeletionJournal(tmp_path / "absent")
    with pytest.raises(ValueError):
        journal.entries()


def test_journal_rejects_extra_fields_and_wrong_filename_hash(tmp_path):
    import json
    from docweave.storage.deletions import DeletionJournal
    journal = DeletionJournal(tmp_path)
    key = journal.record("conversation", uuid4(), uuid4(), [])
    entry = journal.entries()[key]
    entry["message"] = "Private content must never enter this journal"
    (tmp_path / f"{key}.json").write_text(json.dumps(entry))
    with pytest.raises(ValueError):
        journal.entries()


def test_duplicate_intent_flushes_existing_file_before_acknowledging_it(tmp_path, monkeypatch):
    import os
    import stat
    from docweave.storage.deletions import DeletionJournal
    original, synced = os.fsync, []
    def sync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            synced.append(fd)
        original(fd)
    monkeypatch.setattr(os, 'fsync', sync)
    journal = DeletionJournal(tmp_path)
    identity, project = uuid4(), uuid4()
    journal.record('conversation', identity, project, [])
    first = len(synced)
    journal.record('conversation', identity, project, [])
    assert len(synced) > first
