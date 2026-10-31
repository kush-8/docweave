import os
import hashlib
import stat
from pathlib import Path
from uuid import UUID
from docweave.rag.contracts import MAX_BYTES


def snapshot_artifacts(root):
    """Read-only byte fingerprints; refuse links and absent roots during rehearsal."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError("Artifact snapshot requires an existing directory without links")
    result = {}
    def unreadable(error):
        raise error
    for directory, directories, files in os.walk(root, onerror=unreadable, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError("Artifact snapshot cannot follow links")
        for name in files:
            path = Path(directory) / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("Artifact snapshot requires regular files")
            with path.open("rb") as file:
                result[path.relative_to(root).as_posix()] = hashlib.file_digest(file, "sha256").hexdigest()
    return result


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, identity):
        return self.root / str(UUID(str(identity)))

    def put(self, identity, content):
        with self.path(identity).open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

    def read(self, identity):
        with self.path(identity).open("rb") as file:
            content = file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("Oversized artifact")
        return content

    def remove(self, identity):
        self.path(identity).unlink(missing_ok=True)
