"""Offline evidence checks only: no application imports, DB, network or providers."""
import hashlib
import base64
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


CATALOG = Path(__file__).resolve().parents[2] / "catalog"
EXPECTED = {
    "python", "typescript", "react", "nextjs", "tailwindcss", "fastapi", "pydantic",
    "sqlalchemy", "langchain", "langgraph", "huggingface", "vllm", "postgresql",
    "pgvector", "qdrant", "redis", "docker", "github-actions", "terraform", "s3",
    "iam", "ecs", "rds", "opentelemetry", "prometheus", "grafana", "langfuse",
    "pytest", "playwright",
}


def load(name):
    return json.loads((CATALOG / name).read_text(encoding="utf-8"))


def test_all_agreed_entries_have_bounded_attributed_topic_coverage():
    registry = load("required-sources.json")
    entries = registry["entries"]
    assert len(entries) == 29
    assert {entry["id"] for entry in entries} == EXPECTED
    assert registry["fetch_policy"]["max_bytes_per_page"] == 2 * 1024 * 1024
    assert registry["fetch_policy"]["timeout_seconds"] == 10
    assert registry["fetch_policy"]["user_agent"] == "DocWeave/0.1"
    for entry in entries:
        assert entry["name"] and entry["publisher"] and entry["attribution"]
        assert urlsplit(entry["license_or_terms_url"]).scheme == "https"
        assert entry["limitations"] and entry["pages"]
        coverage = entry["version_coverage"]
        assert coverage["kind"] in {"rolling-reference", "source-snapshot"}
        if coverage["kind"] == "source-snapshot":
            assert re.fullmatch(r"[0-9a-f]{40}", entry["source_provenance"]["commit"])
        assert coverage["description"]
        assert coverage["package_match_eligible"] is False
        for page in entry["pages"]:
            uri = urlsplit(page["url"])
            assert uri.scheme == "https" and uri.hostname
            assert not (uri.username or uri.password or uri.query or uri.fragment)
            assert uri.port is None
            assert page["origin"] == f"https://{uri.netloc}"
            assert page["path"] == uri.path and ".." not in uri.path.split("/")
            assert page["url"].startswith(entry["publisher_root"])
            assert page["topics"]


def test_every_bounded_page_has_successful_byte_level_fetch_evidence():
    registry = load("required-sources.json")
    report = load("required-sources-verification.json")
    expected = {(entry["id"], page["url"]) for entry in registry["entries"] for page in entry["pages"]}
    receipts = report["receipts"]
    assert len(receipts) == len(expected) == 85
    assert {(r["entry_id"], r["url"]) for r in receipts} == expected
    for receipt in receipts:
        assert receipt["outcome"] == "verified" and receipt["status"] == 200
        assert receipt["mime"] in {"text/html", "text/plain", "text/markdown"}
        assert 0 < receipt["bytes"] <= registry["fetch_policy"]["max_bytes_per_page"]
        assert re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"])
        assert receipt["title"] and "redirect" not in receipt["title"].lower()
        assert datetime.fromisoformat(receipt["checked_at"]).tzinfo is not None
        assert receipt["robots"]["can_fetch"] is True
        assert 1 <= receipt["robots"]["crawl_delay"] <= 10
        proof = receipt["parse"]
        assert proof["outcome"] == "verified"
        assert re.fullmatch(r"[0-9a-f]{64}", proof["normalized_sha256"])
        assert 0 < proof["characters"] <= 2_000_000
        assert 0 < proof["chunks"] <= 10_000
        assert proof["configuration"]
        expected_media = receipt["mime"]
        if expected_media != "text/html" and urlsplit(receipt["url"]).path.endswith((".md", ".markdown")):
            expected_media = "text/markdown"
        assert receipt["parser_media_type"] == expected_media
        assert proof["configuration"].endswith(":" + expected_media)
        source_root = CATALOG.parent / "src" / "docweave" / "rag"
        assert set(proof["parser_sources_sha256"]) == {"parsing.py", "chunking.py", "contracts.py"}
        for name, source_hash in proof["parser_sources_sha256"].items():
            source = (source_root / name).read_text(encoding="utf-8").encode()
            assert hashlib.sha256(source).hexdigest() == source_hash


def test_evidence_is_bound_to_exact_reviewed_manifest_across_line_endings():
    manifest = (CATALOG / "required-sources.json").read_text(encoding="utf-8")
    report = load("required-sources-verification.json")
    assert hashlib.sha256(manifest.encode("utf-8")).hexdigest() == report["manifest_sha256"]
    assert datetime.fromisoformat(report["checked_at"]).tzinfo is not None


def test_every_page_robots_decision_is_reproducible_from_bounded_policy_evidence():
    spec = importlib.util.spec_from_file_location("evaluate_robots", CATALOG / "evaluate_robots.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = load("required-sources-verification.json")
    assert report["robots_agent"] == module.AGENT == "DocWeave/0.1"
    policies = {p["origin"]: p for p in report["robots"]}
    for receipt in report["receipts"]:
        uri = urlsplit(receipt["url"])
        policy = policies[f"https://{uri.netloc}"]
        assert policy["url"] == policy["origin"] + "/robots.txt"
        assert policy["status"] in (200, 404)
        assert policy["bytes"] <= 262144
        assert re.fullmatch(r"[0-9a-f]{64}", policy["sha256"])
        if policy["status"] == 200:
            body = base64.b64decode(policy["body_base64"], validate=True)
            assert len(body) == policy["bytes"]
            assert hashlib.sha256(body).hexdigest() == policy["sha256"]
        assert module.decision(policy, receipt["url"]) == receipt["robots"]


def test_robots_denials_statuses_agent_specific_rules_and_delays_fail_closed():
    spec = importlib.util.spec_from_file_location("evaluate_robots", CATALOG / "evaluate_robots.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def policy(text, status=200):
        return {"status": status, "body_base64": base64.b64encode(text.encode()).decode()}

    url = "https://publisher.example/docs/page"
    assert module.decision(policy("User-agent: *\nAllow: /"), url)["can_fetch"]
    assert not module.decision(policy("User-agent: DocWeave\nDisallow: /docs/\n\nUser-agent: *\nAllow: /"), url)["can_fetch"]
    assert not module.decision(policy("User-agent: *\nCrawl-delay: 11"), url)["can_fetch"]
    assert module.decision(policy("User-agent: *\nCrawl-delay: 2"), url)["crawl_delay"] == 2
    assert module.decision(policy("", 404), url)["can_fetch"]
    for status in (301, 401, 403, 429, 500):
        assert not module.decision(policy("", status), url)["can_fetch"]
