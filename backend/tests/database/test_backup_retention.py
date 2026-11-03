import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest


CREATED = datetime(2026, 11, 1, tzinfo=timezone.utc)


def recovery(root, name="verified"):
    folder = root / name
    folder.mkdir()
    (folder / "development.dump").write_bytes(b"Synthetic recovery dump")
    (folder / "artifacts").mkdir()
    (folder / "artifacts" / "snapshot").write_bytes(b"Synthetic document")
    (folder / "acceptance.json").write_text(json.dumps({
        "restored_before_migration": True, "rows_match_rehearsal": True,
        "artifacts_preserved": True,
        "backup_sha256": hashlib.sha256(b"Synthetic recovery dump").hexdigest(),
    }))
    return folder


def test_only_enrolled_verified_backup_expires_at_seven_days(tmp_path):
    from docweave.storage.backups import enroll_backup, expire_backups
    folder = recovery(tmp_path)
    archive = tmp_path / "accounting-archive"
    archive.mkdir()
    (archive / "claims.json").write_text("Unsettled claims")
    enroll_backup(tmp_path, folder.name, created_at=CREATED)
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=7, microseconds=-1)) == []
    assert folder.exists()
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=7)) == [
        {"backup": "verified", "status": "deleted"}]
    assert not folder.exists()
    assert (archive / "claims.json").read_text() == "Unsettled claims"


@pytest.mark.parametrize("change", ["changed", "added", "removed"])
def test_changed_seal_preserves_entire_backup(tmp_path, change):
    from docweave.storage.backups import enroll_backup, expire_backups
    folder = recovery(tmp_path)
    enroll_backup(tmp_path, folder.name, created_at=CREATED)
    if change == "changed":
        (folder / "development.dump").write_bytes(b"Different")
    elif change == "added":
        (folder / "later-claims.json").write_text("New evidence")
    else:
        (folder / "artifacts" / "snapshot").unlink()
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=8)) == [
        {"backup": "verified", "status": "blocked"}]
    assert (folder / "acceptance.json").exists()


def test_unverified_dump_or_archive_cannot_be_enrolled(tmp_path):
    from docweave.storage.backups import enroll_backup
    folder = recovery(tmp_path)
    (folder / "acceptance.json").write_text('{"artifacts_preserved": true}')
    with pytest.raises(ValueError):
        enroll_backup(tmp_path, folder.name, created_at=CREATED)
    assert not (folder / ".retention.json").exists()


@pytest.mark.parametrize("name", ["..", "../outside", "nested/backup", "C:/outside", ""])
def test_enrollment_refuses_paths_outside_direct_backup_children(tmp_path, name):
    from docweave.storage.backups import enroll_backup
    with pytest.raises(ValueError):
        enroll_backup(tmp_path, name, created_at=CREATED)


def test_expiry_rejects_links_even_when_receipt_and_bytes_match(tmp_path, monkeypatch):
    from pathlib import Path
    from docweave.storage.backups import enroll_backup, expire_backups
    folder = recovery(tmp_path)
    enroll_backup(tmp_path, folder.name, created_at=CREATED)
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == folder / "artifacts" or original(p))
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=8)) == [
        {"backup": "verified", "status": "blocked"}]
    assert (folder / "development.dump").exists()


def test_corrupt_receipt_and_missing_root_are_safe(tmp_path):
    from docweave.storage.backups import expire_backups
    assert expire_backups(tmp_path / "absent") == []
    folder = recovery(tmp_path)
    (folder / ".retention.json").write_text("not json")
    assert expire_backups(tmp_path) == [{"backup": "verified", "status": "blocked"}]
    assert (folder / "development.dump").exists()


def test_locked_file_resumes_durable_deletion_without_erasing_new_evidence(tmp_path, monkeypatch):
    from pathlib import Path
    from docweave.storage.backups import enroll_backup, expire_backups
    folder = recovery(tmp_path)
    enroll_backup(tmp_path, folder.name, created_at=CREATED)
    original = Path.unlink
    def locked(path, *args, **kwargs):
        if path == folder / "artifacts" / "snapshot":
            raise PermissionError("Synthetic Windows file lock")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", locked)
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=8)) == [
        {"backup": "verified", "status": "retry_pending"}]
    assert not (folder / "development.dump").exists()
    assert json.loads((folder / ".retention.json").read_text())["deleting"] is True
    monkeypatch.setattr(Path, "unlink", original)
    later = folder / "new-claims.json"
    later.write_text("Preserve new evidence")
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=8)) == [
        {"backup": "verified", "status": "blocked"}]
    assert later.exists()
    later.unlink()
    assert expire_backups(tmp_path, now=CREATED + timedelta(days=8)) == [
        {"backup": "verified", "status": "deleted"}]
    assert not folder.exists()


def test_extreme_timestamp_is_blocked_without_stopping_maintenance(tmp_path):
    from docweave.storage.backups import enroll_backup, expire_backups
    folder = recovery(tmp_path)
    enroll_backup(tmp_path, folder.name, created_at=CREATED)
    marker = folder / ".retention.json"
    receipt = json.loads(marker.read_text())
    receipt["created_at"] = "9999-12-31T00:00:00+00:00"
    marker.write_text(json.dumps(receipt))
    assert expire_backups(tmp_path) == [{"backup": "verified", "status": "blocked"}]
    assert (folder / "development.dump").exists()
