"""Content-free, write-before-commit deletion intents outside database backups."""
import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import UUID


class DeletionJournal:
    def __init__(self, root):
        self.root = Path(root).absolute()

    def check_root(self):
        if (not self.root.is_dir() or any(path.is_symlink() or path.is_junction()
            for path in (self.root, *self.root.parents))):
            raise ValueError("Latest deletion journal must exist without links")

    @staticmethod
    def encode(entry):
        if set(entry) != {"format", "kind", "id", "project_id", "artifacts"}:
            raise ValueError("Unexpected deletion journal fields")
        if entry["format"] != "deletion-v1" or entry["kind"] not in ("conversation", "document", "source"):
            raise ValueError("Invalid deletion journal kind")
        if (str(UUID(entry["id"])) != entry["id"] or str(UUID(entry["project_id"])) != entry["project_id"]
            or not isinstance(entry["artifacts"], list)
            or any(str(UUID(item)) != item for item in entry["artifacts"])
            or entry["artifacts"] != sorted(set(entry["artifacts"]))
            or entry["kind"] == "conversation" and entry["artifacts"]):
            raise ValueError("Invalid deletion journal identities")
        data = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
        if len(data) > 64 * 1024:
            raise ValueError("Oversized deletion intent")
        return data

    def record(self, kind, identity, project_id, artifacts):
        self.check_root()
        entry = {"format": "deletion-v1", "kind": kind, "id": str(UUID(str(identity))),
            "project_id": str(UUID(str(project_id))), "artifacts": sorted(set(str(UUID(str(item))) for item in artifacts))}
        data = self.encode(entry)
        key = hashlib.sha256(data).hexdigest()
        path = self.root / f"{key}.json"
        try:
            with path.open("xb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
        except FileExistsError:
            if self.entries().get(key) != entry:
                raise ValueError("Existing deletion intent does not match") from None
            # Another writer can publish complete bytes before its own fsync returns.
            with path.open('r+b') as file:
                os.fsync(file.fileno())
        if os.name != "nt":
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return key

    def entries(self):
        self.check_root()
        result = {}
        for path in self.root.iterdir():
            if path.is_symlink() or path.is_junction() or not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("Deletion journal requires regular files without links")
            with path.open("rb") as file:
                data = file.read(64 * 1024 + 1)
            if len(data) > 64 * 1024:
                raise ValueError("Oversized deletion intent")
            entry = json.loads(data)
            canonical = self.encode(entry)
            key = hashlib.sha256(canonical).hexdigest()
            if path.name != f"{key}.json" or data != canonical:
                raise ValueError("Deletion journal hash or encoding mismatch")
            result[key] = entry
        return result
