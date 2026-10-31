import os
from pathlib import Path
from uuid import UUID
from docweave.rag.contracts import MAX_BYTES


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
