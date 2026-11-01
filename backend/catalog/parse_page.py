"""Parse one ephemeral fetch with the actual application parser; emit metadata only."""
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docweave.rag.parsing import parse_text


request = json.load(sys.stdin)
try:
    parsed = parse_text(base64.b64decode(request["body_base64"], validate=True), request["mime"])
    result = {"outcome": "verified", "normalized_sha256": parsed["sha256"],
              "characters": len(parsed["text"]), "chunks": len(parsed["chunks"]),
              "configuration": parsed["configuration"]}
except (ValueError, UnicodeError) as error:
    result = {"outcome": "failed", "error": str(error)}
source_root = Path(__file__).resolve().parents[1] / "src" / "docweave" / "rag"
result["parser_sources_sha256"] = {
    name: hashlib.sha256((source_root / name).read_text(encoding="utf-8").encode()).hexdigest()
    for name in ("parsing.py", "chunking.py", "contracts.py")
}
print(json.dumps(result))
