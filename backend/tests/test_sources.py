"""Approved selections, address pinning and redirect scope are fetch authority."""

import json
import socket
import asyncio
import subprocess
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from test_auth import auth_client  # noqa: F401
from test_collections import collections  # noqa: F401
from test_database import databases, test_urls  # noqa: F401
from test_ingestion import FIXTURES, ingestion, work  # noqa: F401
from test_memberships import members  # noqa: F401

pytestmark = pytest.mark.anyio


def selection(**changes):
    return {"source_url": "https://docs.example.test/manual/setup.md", "origin": "https://docs.example.test",
        "path_prefix": "/manual/", "attribution": "Publisher; approved test documentation", **changes}


def public_resolver(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


@pytest.mark.parametrize("url", ["http://docs.example.test/manual/a.md", "https://user:pass@docs.example.test/manual/a.md",
    "https://docs.example.test:444/manual/a.md", "https://evil.test/manual/a.md", "https://docs.example.test/other/a.md",
    "https://docs.example.test/manual/../secret", "https://docs.example.test/manual/%2e%2e/secret",
    "https://docs.example.test/manual/%252e%252e/secret", "https://docs.example.test/manual/a%2fb", "https://docs.example.test/manual/a?secret=x"])
async def test_fetch_scope_rejects_unapproved_or_ambiguous_targets(url):
    from docweave.sources import validated_address
    with pytest.raises(ValueError):
        validated_address(url, selection(), resolver=public_resolver)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "fc00::1", "0.0.0.0", "192.0.2.1", "224.0.0.1", "ff02::1", "64:ff9b::7f00:1"])
async def test_dns_results_are_all_public_before_a_connection_is_allowed(address):
    from docweave.sources import validated_address
    def mixed(host, port, **kwargs):
        return public_resolver(host, port) + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    with pytest.raises(ValueError):
        validated_address(selection()["source_url"], selection(), resolver=mixed)


async def test_safe_target_returns_pinned_address_without_second_dns_lookup():
    from docweave.sources import validated_address
    assert validated_address(selection()["source_url"], selection(), resolver=public_resolver) == ("docs.example.test", 443, "93.184.216.34")


async def approved_selection(c, **changes):
    identity = uuid4()
    data = selection(**changes)
    async with c["owner"].begin() as connection:
        await connection.execute(text("""INSERT INTO app.documentation_selections(id,workspace_id,project_id,approved_by,
            technology,docs_target,coverage,source_url,origin,path_prefix,attribution,approved_stack)
            VALUES(:id,:workspace,:project,:actor,'FastAPI','rolling:2026-10-31',
                CAST(:coverage AS jsonb),:source_url,:origin,:path_prefix,:attribution,
                (SELECT selected FROM app.projects p CROSS JOIN LATERAL jsonb_array_elements(p.stack) selected
                    WHERE p.id=:project AND lower(selected->>'technology')='fastapi' LIMIT 1))"""),
            {"id": identity, "workspace": UUID(c["workspace"]["id"]), "project": UUID(c["project"]), "actor": UUID(c["user"]["id"]),
                "coverage": json.dumps({"granularity": "rolling", "publisher_range": None}), **data})
    return identity


async def import_source(c, identity, **changes):
    return await c["admin"].post(f'/api/v1/projects/{c["project"]}/sources',
        json={"source_selection_id": str(identity), "collection_id": c["collection"], **changes}, headers=c["headers"])


async def test_import_only_accepts_immutable_approved_same_project_selections(ingestion):
    c = ingestion
    identity = await approved_selection(c)
    assert (await import_source(c, identity, trusted_url="https://evil.test")).status_code == 422
    assert (await import_source(c, uuid4())).status_code == 404
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.documentation_selections SET active=false WHERE id=:id"), {"id": identity})
    assert (await import_source(c, identity)).status_code == 404
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.documentation_selections SET active=true WHERE id=:id"), {"id": identity})
    accepted = await import_source(c, identity)
    assert accepted.status_code == 202, accepted.text
    async def fetcher(stored):
        assert stored["id"] == str(identity)
        return b"# Official\n\nUse a database session dependency.\n", "text/markdown"
    await work(c, accepted.json()["job_id"], fetcher=fetcher)
    sources = (await c["admin"].get(f'/api/v1/projects/{c["project"]}/sources')).json()["items"]
    assert len(sources) == 1 and sources[0]["coverage"] == {"granularity": "rolling", "publisher_range": None}
    assert sources[0]["accepted_pages"] == 1
    source = sources[0]
    refreshed = await c["admin"].post(f'/api/v1/sources/{source["id"]}/refresh', headers=c["headers"])
    assert refreshed.status_code == 202
    async def failed_fetch(stored):
        raise ValueError("Unsafe redirect")
    await work(c, refreshed.json()["job_id"], fetcher=failed_fetch)
    sources = (await c["admin"].get(f'/api/v1/projects/{c["project"]}/sources')).json()["items"]
    assert sources[0]["status"] == "stale" and sources[0]["accepted_pages"] == 1


async def test_revoked_selection_never_reaches_fetch_and_source_delete_tombstones(ingestion):
    c = ingestion
    identity = await approved_selection(c)
    accepted = (await import_source(c, identity)).json()
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.documentation_selections SET active=false WHERE id=:id"), {"id": identity})
    async def forbidden(*args):
        pytest.fail("Revoked selection reached fetch")
    await work(c, accepted["job_id"], fetcher=forbidden)
    assert (await c["admin"].get(accepted["status_url"])).json()["status"] == "blocked_policy"
    source = (await c["admin"].get(f'/api/v1/projects/{c["project"]}/sources')).json()["items"][0]
    response = await c["admin"].delete(f'/api/v1/sources/{source["id"]}', headers=c["headers"])
    assert response.status_code == 202
    assert (await import_source(c, identity)).status_code == 404


@pytest.mark.parametrize("response", ["redirect", "robots_denied"])
async def test_fetcher_enforces_robots_redirects_and_response_bounds(monkeypatch, response):
    from docweave import sources
    monkeypatch.setattr(sources.socket, "getaddrinfo", public_resolver)
    requests = []
    def request(url, address):
        requests.append(url)
        if url.endswith("/robots.txt"):
            rules = b"User-agent: *\nDisallow: /manual/" if response == "robots_denied" else b"User-agent: *\nAllow: /"
            return 200, {"Content-Type": "text/plain"}, rules
        if response == "redirect":
            return 302, {"Location": "https://evil.test/secret"}, b""
        raise AssertionError("Unexpected HTTP request")
    monkeypatch.setattr(sources, "_request", request)
    with pytest.raises(ValueError):
        await sources.fetch_document(selection())
    assert all(url.startswith("https://docs.example.test/") for url in requests)
    if response == "robots_denied":
        assert len(requests) == 1


async def test_operator_seed_checks_current_owner_and_commits_project_scoped_selection(ingestion):
    c = ingestion
    from docweave.ingestion import ROOT
    sql = (ROOT / "backend" / "catalog" / "pilot-text-selections.sql").read_bytes()
    command = ["docker", "compose", "exec", "-T", "test-db", "psql", "-U", "docweave_migrator", "-d", "docweave_test",
        "-v", "ON_ERROR_STOP=1", "-v", "workspace_id=" + c["workspace"]["id"], "-v", "project_id=" + c["project"], "-v"]
    denied = await asyncio.to_thread(subprocess.run, command + ["approved_by=" + c["recipient"]["id"]], input=sql, capture_output=True, timeout=10)
    assert denied.returncode != 0
    accepted = await asyncio.to_thread(subprocess.run, command + ["approved_by=" + c["user"]["id"]], input=sql, capture_output=True, timeout=10)
    assert accepted.returncode == 0
    async with c["owner"].connect() as connection:
        selected = (await connection.execute(text("SELECT project_id,coverage FROM app.documentation_selections"))).one()
    assert selected.project_id == UUID(c["project"])
    assert selected.coverage == {"granularity": "rolling", "publisher_range": None}
    async with c["owner"].begin() as connection:
        await connection.execute(text("UPDATE app.documentation_selections SET active=false"))
    repeated = await asyncio.to_thread(subprocess.run, command + ["approved_by=" + c["user"]["id"]], input=sql, capture_output=True, timeout=10)
    assert repeated.returncode == 0
    async with c["owner"].connect() as connection:
        assert (await connection.execute(text("SELECT active FROM app.documentation_selections"))).scalars().all() == [False]


async def test_deleting_source_document_cannot_be_undone_by_import_retry(ingestion):
    c = ingestion
    identity = await approved_selection(c)
    accepted = (await import_source(c, identity)).json()
    async with c["owner"].connect() as connection:
        document = await connection.scalar(text("SELECT document_id FROM app.ingestion_jobs WHERE id=:id"), {"id": UUID(accepted["job_id"])})
    assert (await c["admin"].delete(f"/api/v1/documents/{document}", headers=c["headers"])).status_code == 202
    assert (await import_source(c, identity)).status_code == 404
