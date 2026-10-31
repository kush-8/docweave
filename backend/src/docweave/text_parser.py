"""Standard-library-only entry point for the isolated parser image."""

import json, sys
from pathlib import Path


if __name__ == "__main__":
    # -I excludes the script directory; add only the image's trusted package root.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from docweave.rag.contracts import MAX_BYTES
    from docweave.rag.parsing import parse_text

    try:
        sys.stdout.write(json.dumps(parse_text(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1]), ensure_ascii=True))
    except (ValueError, UnicodeError, IndexError):
        sys.exit(2)
