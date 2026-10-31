"""Keep HTTP and workflow dependencies from leaking back into lower layers."""

import ast
from docweave.core.paths import ROOT


def test_lower_layers_do_not_import_http_or_application_composition():
    package = ROOT / "backend/src/docweave"
    violations = []
    for directory in ("core", "schemas", "services", "repositories", "db", "rag", "integrations", "storage", "evaluation"):
        for path in package.joinpath(directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = [node.module or ""] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names] if isinstance(node, ast.Import) else []
                for module in modules:
                    if module.split(".")[0] in ("fastapi", "starlette") or module.startswith(("docweave.api", "docweave.main")):
                        violations.append(f"{path.relative_to(package)}:{node.lineno}: {module}")
                    if directory in ("repositories", "integrations") and module.startswith("docweave.services"):
                        violations.append(f"{path.relative_to(package)}:{node.lineno}: {module}")
                    if directory in ("repositories", "integrations") and module.startswith("docweave.rag.") and module not in ("docweave.rag.contracts", "docweave.rag.prompts"):
                        violations.append(f"{path.relative_to(package)}:{node.lineno}: {module}")
    assert violations == []


def test_sql_stays_in_persistence_and_database_infrastructure():
    package = ROOT / "backend/src/docweave"
    violations = []
    for directory in ("api", "services", "rag", "integrations", "workers"):
        for path in package.joinpath(directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy") and any(item.name in ("text", "select", "insert", "update", "delete") for item in node.names):
                    violations.append(f"{path.relative_to(package)}:{node.lineno}")
    assert violations == []
