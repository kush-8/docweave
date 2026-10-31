"""Versioned source fingerprint over sorted repository-relative paths and bytes."""

import hashlib, json
from pathlib import Path
from docweave.core.paths import ROOT


FINGERPRINT_ALGORITHM = "sha256-path-content-manifest-v1"

def source_fingerprint(root=ROOT, paths=None):
    root = Path(root).resolve()
    if paths is None:
        package = root / "backend" / "src" / "docweave"
        paths = [*package.joinpath("rag").rglob("*.py"), *package.joinpath("repositories", "rag").rglob("*.py"),
            package / "integrations" / "gemini.py", package / "integrations" / "groq.py"]
    files = {}
    for path in paths:
        path = Path(path)
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    files = dict(sorted(files.items()))
    manifest = json.dumps(files, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"algorithm": FINGERPRINT_ALGORITHM, "files": files, "sha256": hashlib.sha256(manifest).hexdigest()}
