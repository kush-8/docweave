"""Seven-day expiry for explicitly enrolled, sealed recovery directories."""
import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docweave.core.paths import ROOT
from docweave.storage.artifacts import snapshot_artifacts


RECEIPT = ".retention.json"


def backup_path(root, name):
    root = Path(root).absolute()
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError("Backup root must be an existing directory without links")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Backup must be a direct child directory")
    path = root / name
    if path.is_symlink() or path.is_junction() or not path.is_dir() or path.resolve().parent != root.resolve():
        raise ValueError("Backup must be a direct child directory without links")
    return path


def read_receipt(path):
    with path.open("rb") as file:
        data = file.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Oversized backup receipt")
    return json.loads(data)


def enroll_backup(root, name, *, created_at):
    path = backup_path(root, name)
    if created_at.tzinfo is None or created_at > datetime.now(timezone.utc):
        raise ValueError("Backup creation time must be a past timezone-aware timestamp")
    files = snapshot_artifacts(path)
    if RECEIPT in files:
        raise ValueError("Backup is already enrolled")
    acceptance = read_receipt(path / "acceptance.json")
    if (acceptance.get("restored_before_migration", acceptance.get("actual_restore_verified")) is not True
        or acceptance.get("rows_match_rehearsal", acceptance.get("original_rows_preserved_except_revision")) is not True
        or acceptance.get("artifacts_preserved") is not True
        or files.get("development.dump") != acceptance.get("backup_sha256", acceptance.get("dump_sha256"))
        or "development.dump" not in files):
        raise ValueError("Backup requires matching dump and successful restore/preservation evidence")
    receipt = {"format": "backup-retention-v1", "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "files": files}
    with (path / RECEIPT).open("x", encoding="utf-8") as file:
        json.dump(receipt, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    return {"backup": name, "expires_at": (created_at + timedelta(days=7)).isoformat()}


def expire_backups(root, *, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root).absolute()
    if not root.exists():
        return []
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError("Backup root cannot be a link")
    results = []
    for child in sorted(root.iterdir()):
        # Never classify or enroll archives based on their names, age or contents.
        if child.is_symlink() or child.is_junction():
            continue
        if not child.is_dir() or not (child / RECEIPT).exists():
            continue
        deleting = False
        try:
            path = backup_path(root, child.name)
            marker = path / RECEIPT
            if marker.is_symlink() or marker.is_junction():
                raise ValueError("Backup receipt cannot be a link")
            receipt = read_receipt(marker)
            created_at = datetime.fromisoformat(receipt["created_at"])
            if receipt["format"] != "backup-retention-v1" or created_at.tzinfo is None:
                raise ValueError("Invalid backup receipt")
            if now < created_at + timedelta(days=7):
                continue
            files = snapshot_artifacts(path)
            del files[RECEIPT]
            deleting = receipt.get("deleting", False)
            if type(deleting) is not bool or not isinstance(receipt["files"], dict) or not receipt["files"]:
                raise ValueError("Invalid deletion state")
            if (not deleting and files != receipt["files"]
                or deleting and any(receipt["files"].get(name) != digest for name, digest in files.items())):
                raise ValueError("Sealed backup changed; preserve it for operator review")
            if not deleting:
                receipt["deleting"] = True
                with marker.open("w", encoding="utf-8") as file:
                    json.dump(receipt, file, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                deleting = True
            # Sealed backups must have no writers; unlink only verified files, never recursively purge new evidence.
            for name in files:
                target = path / name
                if not target.resolve().is_relative_to(path.resolve()):
                    raise ValueError("Backup file escaped the verified directory")
                target.unlink()
            for directory, _, _ in os.walk(path, topdown=False, followlinks=False):
                if Path(directory) != path:
                    Path(directory).rmdir()
            marker.unlink()
            try:
                path.rmdir()
            except OSError:
                with marker.open("x", encoding="utf-8") as file:
                    json.dump(receipt, file, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                raise
            results.append({"backup": child.name, "status": "deleted"})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            results.append({"backup": child.name,
                "status": "retry_pending" if deleting and isinstance(error, OSError) else "blocked"})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "backups")
    parser.add_argument("--enroll", help="Explicitly enroll a verified ordinary recovery backup; never an accounting archive")
    parser.add_argument("--created-at", help="Actual backup creation timestamp with UTC offset, required for enrollment")
    args = parser.parse_args()
    try:
        if args.enroll:
            if not args.created_at:
                raise ValueError("Creation time is required")
            result = enroll_backup(args.root, args.enroll, created_at=datetime.fromisoformat(args.created_at))
        else:
            result = expire_backups(args.root)
        print(json.dumps(result))
        if isinstance(result, list) and any(item["status"] != "deleted" for item in result):
            parser.exit(1)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        parser.exit(2, "Backup retention unavailable; inspect sealed backup paths and private acceptance evidence.\n")


if __name__ == "__main__":
    main()
