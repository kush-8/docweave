"""The parser image entry runs with no site packages or inherited import path."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from docweave.rag.parsing import parse_text


def test_parser_image_copy_set_runs_under_isolated_standard_library_python(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src" / "docweave"
    package = tmp_path / "docweave"
    (package / "rag").mkdir(parents=True)
    shutil.copyfile(source / "text_parser.py", package / "text_parser.py")
    for name in ("__init__.py", "contracts.py", "chunking.py", "parsing.py"):
        shutil.copyfile(source / "rag" / name, package / "rag" / name)
    content = b"\xef\xbb\xbf# Heading\r\n\r\nText.\rMore text.\n"
    result = subprocess.run([sys.executable, "-I", "-S", str(package / "text_parser.py"), "text/markdown"],
        input=content, capture_output=True, timeout=10, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == parse_text(content, "text/markdown")
    assert json.loads(result.stdout)["configuration"] == "utf8-lf:headings:whitespace350-overlap50:v1:text/markdown"


@pytest.mark.parametrize("content,media_type", [(b"\xff", "text/plain"), (b"a\x00b", "text/plain"),
    (b" ", "text/plain"), (b"text", "application/pdf")])
def test_isolated_parser_rejects_invalid_input_with_exit_two(content, media_type):
    entry = Path(__file__).resolve().parents[1] / "src" / "docweave" / "text_parser.py"
    result = subprocess.run([sys.executable, "-I", "-S", str(entry), media_type], input=content,
        capture_output=True, timeout=10)
    assert result.returncode == 2
    assert result.stdout == b""
